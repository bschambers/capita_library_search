"""Gets information from the Islington Libraries Catalogue."""

from requests import get
from requests.exceptions import RequestException
from contextlib import closing
from bs4 import BeautifulSoup
from io import StringIO
import re
import sys
import argparse

def log_error(e):
    """
    It is always a good idea to log errors.
    This function just prints them, but you can
    make it do anything.
    """
    print(e)

def simple_get(url):
    """
    Attempts to get the content at `url` by making an HTTP GET request.
    If the content-type of response is some kind of HTML/XML, return the
    text content, otherwise return None.
    """
    try:
        with closing(get(url, stream=True)) as resp:
            if is_good_response(resp):
                return resp.content
            else:
                return None

    except RequestException as e:
        log_error('Error during requests to {0} : {1}'.format(url, str(e)))
        return None

def is_good_response(resp):
    """
    Returns True if the response seems to be HTML, False otherwise.
    """
    content_type = resp.headers['Content-Type'].lower()
    return (resp.status_code == 200
            and content_type is not None
            and content_type.find('html') > -1)

class CatalogueItem(object):
    """Represents a library catalogue item."""

    item_id = 'default'
    title = 'default'
    publisher = 'default'
    link = 'default'
    summary = 'default'
    available = 'default'
    branches = []

    def to_string(self):
        s = StringIO()
        s.write('ID:        {}\n'.format(self.item_id))
        s.write('TITLE:     {}\n'.format(self.title))
        s.write('PUBLISHER: {}\n'.format(self.publisher))
        s.write('LINK:      {}\n'.format(self.link))
        s.write('SUMMARY:   {}\n'.format(self.summary))
        s.write('AVAILABLE: {}'.format(self.available))
        for b in branches:
            s.write('')
        return s.getvalue()

class IslingtonSearch(object):
    """Get search results from Islington Library Catalogue."""

    islington_url = 'https://capitadiscovery.co.uk/islington/'
    search_url = ''
    items_found = []

    def __init__(self, title='', author=''):

        if not (title or author):
            log_error('IslingtonSearch: must supply title and/or author\n')
            return

        # build search url
        self.search_url = self.islington_url + 'items?query='
        if title:
            self.search_url += 'title%3A%28' + title + '%29'
        if author:
            if title:
                self.search_url += '+AND+'
            self.search_url += 'author%3A%28' + author + '%29'
        self.search_url += '#availability'

        # get website
        raw_html = simple_get(self.search_url)
        html = BeautifulSoup(raw_html, 'html.parser')

        # extract info

        for search_results in html.select('div#searchResults'):

            for div in search_results.select('div.summary'):
                new_item = CatalogueItem()

                h2 = div.select('h2.title')
                if h2:
                    a = h2[0].select('a')
                    if a:
                        new_item.title = a[0].get('title', 'NOT FOUND')
                        temp_link = a[0].get('href', 'NOT FOUND')
                        match_obj = re.search(r'items/([0-9]+)\?', temp_link)
                        if match_obj:
                            new_item.item_id = match_obj.group(1)
                            new_item.link = self.islington_url + 'items/' + new_item.item_id

                div_pub = div.select('div.publisher')
                if div_pub:
                    span = div_pub[0].select('span.publisher')
                    if span:
                        new_item.publisher = span[0].text

                div_summ = div.select('div.summarydetail')
                if div_summ:
                    span = div_summ[0].select('span.summarydetail')
                    if span:
                        new_item.summary = span[0].text

                # availability
                html = BeautifulSoup(simple_get(new_item.link), 'html.parser')
                div_avail = html.select('div#availability')
                if div_avail:
                    div_status = div_avail[0].select('div.status')
                    if div_status:
                        p = div_status[0].select('p.branches')
                        if p:
                            new_item.available = p[0].text

                self.items_found.append(new_item)

if __name__ == '__main__':
    # using argparse to get the command line args
    parser = argparse.ArgumentParser(description='Search Islington Library Catalogue')
    parser.add_argument('--title', '-t', metavar='T', type=str, nargs=1)
    parser.add_argument('--author', '-a', metavar='A', type=str, nargs=1)
    args = parser.parse_args()
    title = args.title
    author = args.author
    # argparse get the args as lists
    if isinstance(title, list): title = title[0]
    if isinstance(author, list): author = author[0]

    print('\nSEARCHING: title="{}", author="{}"\n'.format(title, author))
    search = IslingtonSearch(title, author)
    count = 0
    for item in search.items_found:
        count += 1
        print('ITEM {}:\n{}\n'.format(count, item.to_string()))

    print('{} ITEMS FOUND'.format(len(search.items_found)))
    print('\nUSING SEARCH URL: {}\n'.format(search.search_url))
    print('title = {}'.format(title))
    print('author = {}\n'.format(author))
