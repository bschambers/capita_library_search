# Copyright 2019-present, B. S. Tancham --- Distributed under GPL version 3

"""Get search information from capitadiscovery based library catalogue websites
by web-scraping with BeautifulSoup.

USAGE:

 $ python -i plscrape.py -t "diary of a nobody" -a grossmith -l islington

NOTE: Using -i option to enter into interactive python interpreter after running
the script. This way the search-results object can be queried interactively
after the search is done. If you want it to just print the results to the
terminal and then quit, leave out the -i option.

"""

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
    """A library catalogue item."""

    def __init__(self):
        self.status = ''
        self.barcode = 0
        self.shelfmark = ''
        self.item_type = ''

    def is_available(self):
        return self.status.lower() == 'available'

    def to_string(self):
        return 'status={} | barcode={} | shelfmark={} | type={}'.format(self.status,
                                                                        self.barcode,
                                                                        self.shelfmark,
                                                                        self.item_type)

class BranchResultItem(object):
    """A search results item's library branch detail."""

    def __init__(self):
        self.name = ''
        self.items = [] # list of CatalogueItem

    def add_item(self, cat_item):
        "cat_item = a CatalogueItem"
        self.items.append(cat_item)

    def is_available(self):
        for i in self.items:
            if i.is_available():
                return True
        return False

    def to_string(self):
        available = ' (AVAILABLE)' if self.is_available() else ''
        s = StringIO()
        s.write('... BRANCH: {}{}\n'.format(self.name, available))
        for i in self.items:
            s.write('... ... {}\n'.format(i.to_string()))
        return s.getvalue()

class SearchResultItem(object):
    """A search results item."""

    def __init__(self):
        self.item_id = 'default'
        self.title = 'default'
        self.publisher = 'default'
        self.link = 'default'
        self.summary = 'default'
        self.available = 'default'
        self.branches = []

    def add_branch_result(self, bri):
        "bri = a BranchResultItem"
        self.branches.append(bri)

    def to_string(self):
        s = StringIO()
        s.write('ID:        {}\n'.format(self.item_id))
        s.write('TITLE:     {}\n'.format(self.title))
        s.write('PUBLISHER: {}\n'.format(self.publisher))
        s.write('LINK:      {}\n'.format(self.link))
        s.write('SUMMARY:   {}\n'.format(self.summary))
        s.write('AVAILABLE: {}\n'.format(self.available))
        for b in self.branches:
            s.write(b.to_string())
        return s.getvalue()

class PLSearch(object):
    """Get search results from Library Catalogue website.

    Abstract Base Class.
    """

    title = ''
    author = ''
    libservice = ''
    catalogue_url = ''
    search_url = ''
    items_found = [] # a list of SearchResultItem
    error_messages = []

    def run_search(self, site_engine, libservice, title='', author=''):
        self.catalogue_url = site_engine.get_catalogue_url(libservice);
        self.title = title
        self.author = author

        if not (title or author):
            log_error('PLSearch: must supply title and/or author\n')
            return

        self.search_url = site_engine.build_search_url(self.catalogue_url, self.title, self.author)

        print("RUN SEARCH:")
        print(f"title={self.title}")
        print(f"author={self.author}")
        print(f"catalogue url={self.catalogue_url}")
        print(f"search url={self.search_url}")

        # get website and parse html with BeautifulSoup
        raw_html = simple_get(self.search_url)
        if not raw_html:
            self.error_message = "could not get web page"
            return
        html = BeautifulSoup(raw_html, 'html.parser')

        # extract info
        self.items_found = site_engine.get_search_results(html)

class CapitaEngine(object):
    """Site-Engine for capitadiscovery websites."""

    capita_url = 'https://capitadiscovery.co.uk/'

    def get_catalogue_url(self, libservice):
        return self.capita_url + libservice + '/'

class PrismEngine(object):
    """Site-Engine for prism.librarymanagementcloud websites."""

    prism_url = 'https://prism.librarymanagementcloud.co.uk/'

    def get_catalogue_url(self, libservice):
        return self.prism_url + libservice + '/'

    def build_search_url(self, catalogue_url, title='', author=''):
        """Get search url in this format:

        https://prism.librarymanagementcloud.co.uk/islington/items?query=diary+of+a+nobody
        https://prism.librarymanagementcloud.co.uk/islington/items?query=+title%3A%28diary+of+a+nobody%29
        https://prism.librarymanagementcloud.co.uk/islington/items?query=+author%3A%28grossmith%29+AND+title%3A%28diary+of+a+nobody%29
        """
        title_str = ''
        author_str = ''
        if title:
            title_str = '+title%3A%28' + title.replace(' ', '+') + '%29'
        if author:
            author_str = '+author%3A%28' + author.replace(' ', '+') + '%29'
        url = catalogue_url + 'items?query=' + title_str
        if author_str:
            url += '+AND'
        url += author_str
        return url

    def get_search_results(self, html):
        items_found = []
        for search_results in html.select('div#searchResults'):
            # get direct child nodes
            for record in search_results.find_all(recursive=False):
                print("\nNEXT ITEM:")
                item = SearchResultItem()

                # link
                # id
                item.link = record.get('id', 'NOT FOUND')
                match_obj = re.search(r'items/([0-9]+)', item.link)
                if match_obj:
                    item.item_id = match_obj.group(1)

                div_list = record.select('div.summary')
                if div_list:
                    div = div_list[0]

                    # title
                    h2 = div.select('h2.title')
                    if h2:
                        a = h2[0].select('a')
                        if a:
                            item.title = a[0].get('title', 'NOT FOUND')

                    # publisher
                    div_pub = div.select('div.publisher')
                    if div_pub:
                        span = div_pub[0].select('span.publisher')
                        if span:
                            item.publisher = span[0].text

                    # summary
                    div_summ = div.select('div.summarydetail')
                    if div_summ:
                        span = div_summ[0].select('span.summarydetail')
                        if span:
                            item.summary = span[0].text

                    # availability
                    html = BeautifulSoup(simple_get(item.link), 'html.parser')
                    item.available = 'NOT AVAILABLE'
                    div_avail = html.select('div#availability')
                    if div_avail:

                        avail_status = div_avail[0].select('div.status')
                        if avail_status:
                            p_branches = avail_status[0].select('p.branches')
                            if p_branches:
                                item.available = p_branches[0].text

                        # branch result details
                        ul_options = div_avail[0].select('ul.options')
                        if ul_options:
                            li_branches = ul_options[0].select('li')
                            for lib in li_branches:
                                bri = self.get_branch_result_item(lib)
                                item.add_branch_result(bri)

                print(item.to_string())
                items_found.append(item)

            print(f"... found {len(items_found)} items")
        return items_found

    def get_branch_result_item(self, branch):

        bri = BranchResultItem()

        # <span itemprop="name">
        name_span = branch.findAll('span', {"itemprop" : "name"})
        if name_span:
            bri.name = name_span[0].text

            # <tbody> - table body contains the items
            tbody = branch.select('tbody')
            if tbody:
                # each <tr> is a CatalogueItem
                for row in tbody[0].select('tr'):
                    citem = CatalogueItem()

                    prop = row.findAll('span', {'itemprop' : 'serialNumber'})
                    if prop:
                        citem.barcode = prop[0].text

                    prop = row.findAll('span', {'itemprop' : 'sku'})
                    if prop:
                        citem.shelfmark = prop[0].text

                    prop = row.findAll('td', {'class' : 'loan'})
                    if prop:
                        citem.item_type = prop[0].text

                    prop = row.findAll('td', {'class' : re.compile(r'item-status .*')})
                    if prop:
                        citem.status = prop[0].text
                        citem.status = citem.status.strip()

                    bri.add_item(citem)

        return bri

def show_search(search):
    """Prints summary of a search to standard output.

Arguments:
    search -- a PLSearch object
    """

    count = 0
    for item in search.items_found:
        count += 1
        print('ITEM {}:\n{}\n'.format(count, item.to_string()))

    print('{} ITEMS FOUND'.format(len(search.items_found)))
    print('\nUSING SEARCH URL: {}\n'.format(search.search_url))
    print('title = {}'.format(search.title))
    print('author = {}'.format(search.author))
    print('library service = {}\n'.format(search.libservice))

    if search.error_messages:
        for msg in search.error_messages:
            print(f'ERROR: {msg}\n')

def do_search(libservice, title, author):
    print(f'\nSEARCHING: library-service="{libservice}", title="{title}", author="{author}"\n')
    # search = CapitaSearch(title, author, libservice)
    search = PLSearch()
    search.run_search(PrismEngine(), libservice=libservice, title=title, author=author)
    show_search(search)
    return search

def do_search_from_file(filename):
    print('\nDO SEARCH FROM FILE: \n'.format(filename))
    backend = PrismEngine()
    libservice = ""
    author = ""
    title = ""
    search_results = []
    # open the file and process it line by line
    # using 'with' means that the file is properly closed, even if an exception is raised
    with open(filename, 'r') as f:
        for line in f:
            # strip whitespace and newlines from front and back
            # also convert to lowercase
            line = line.strip().lower()
            # ignore empty lines and comments
            if line == "" or line[0] == "#":
                pass
            else:
                # each line should consist of two parts:
                # 1: a parameter name (l, a, t)
                # 2: the parameter value
                parts = line.split("=")
                if len(parts) != 2:
                    log_error(f'ERROR in do_search_from_file: line "{line}" is not a proper parameter/value pair.')
                else:

                    # get first word of line (it should be a parameter name)
                    param = parts[0].strip()
                    # rest of line is the content
                    value = parts[1].strip()

                    if param == 'l' or param == 'library' or param == 'libraryservice':
                        libservice = value
                        print(f'libservice set to "{libservice}"')

                    elif param == 'a' or param == 'author':
                        author = value
                        print(f'author set to "{author}"')

                    elif param == 't' or param == 'title':
                        title = value
                        print(f'title set to "{title}"')
                        search = PLSearch()
                        search.run_search(backend, libservice=libservice, title=title, author=author)
                        search_results = search_results + [search]
                        show_search(search)

                    else:
                        log_error(f'ERROR in do_search_from_file: parameter "{param}" not recognised.')

    return search_results

def write_output_file_html(results):
    """Presents the results nicely in an HTML file.

Arguments:
    results -- a list of PLSearch objects
"""
    print("\n... writing results to file: output.html...\n\n")
    libservice = ""
    with open('output.html', 'w') as f:
        f.write("<!DOCTYPE html>\n")
        f.write("<html>\n")
        f.write("<head>\n")
        f.write("<title>PLScrape: Search Results</title>\n")
        f.write("</head>\n")
        f.write("<body>\n")
        for search in results:
            if search.libservice != libservice:
                f.write(f'<h1>LIBRARY SERVICE: {search.libservice}')
                libservice = search.libservice
            f.write("<h2>TITLE: {}, AUTHOR: {}</h2>\n".format(search.title, search.author))
            f.write("<p>{} records found</p>".format(len(search.items_found)))
            if len(search.items_found) > 0:
                f.write("<ol>")
                for item in search.items_found:
                    available = item.available
                    title = item.title
                    branches = item.branches
                    f.write("<li>{} / {} / {}</li>".format(available, title,  branches))
                    # f.write("<li>{} / {} / {}".format(available, title,  branches))
                    # if len(item.branches) > 0:
                    #     f.write("<ol")
                    #     for cat_item in item.branches:
                    #         f.write("<li>{}</li>".format(cat_item.to_string()))
                    #     f.write("</ol>")
                    # f.write("</li>")
                f.write("</ol>")
        f.write("</body>\n")
        f.write("</html>\n")

if __name__ == '__main__':
    # using argparse to get the command line args
    parser = argparse.ArgumentParser(description='Search Islington Library Catalogue')
    parser.add_argument('--title', '-t', metavar='T', type=str, nargs=1)
    parser.add_argument('--author', '-a', metavar='A', type=str, nargs=1)
    parser.add_argument('--libservice', '-l', metavar='L', type=str, nargs=1)
    parser.add_argument('--filename', '-f', metavar='F', type=str, nargs=1)
    args = parser.parse_args()
    filename = args.filename
    libservice = args.libservice
    title = args.title
    author = args.author
    # argparse gets the args as lists - let's just take the first elements
    if isinstance(title, list): title = title[0]
    if isinstance(author, list): author = author[0]
    if isinstance(libservice, list): libservice = libservice[0]
    if isinstance(filename, list): filename = filename[0]

    results = []

    if filename:
        results = do_search_from_file(filename)
    else:
        if not libservice:
            print("Please specify the library service to search, or provide an input file.")
            exit(1)
        if not (title or author):
            print("Please specify a title and/or an author.")
            exit(1)
        search = do_search(libservice, title, author)
        results = [search]

    write_output_file_html(results)
