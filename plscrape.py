# Copyright 2019-present, B. S. Tancham --- Distributed under GPL version 3

"""Get search information from public library catalogue websites by web-scraping
with BeautifulSoup.

USAGE:

 $ python -i plscrape.py -l islington -a grossmith -t "diary of a nobody"

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
from datetime import datetime
import re
import sys
import argparse

# global variables
config_filename = '.plscrape'
backends_dict = {}
library_service_backends = {}
match_exact = True
backend_id_prism = 'prism.librarymanagementcloud.co.uk'
backend_id_llc_sirsidynix = 'llc.ent.sirsidynix.net.uk'

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
    """Returns True if the response seems to be HTML, False otherwise."""
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
        self.item_id = '?' # i.e. bib record number
        self.link = '?'
        self.title = '?'
        self.publisher = '?'
        self.publication_date = '?'
        self.item_type = '?'
        self.summary = '?'
        self.available_at = '?'
        self.branches = []

    def add_branch_result(self, bri):
        """bri = a BranchResultItem"""
        self.branches.append(bri)

    def to_string(self):
        s = StringIO()
        s.write('ID:        {}\n'.format(self.item_id))
        s.write('TITLE:     {}\n'.format(self.title))
        s.write(f'TYPE: {self.item_type}\n')
        s.write('PUBLISHER: {}\n'.format(self.publisher))
        s.write(f'DATE: {self.publication_date}\n')
        s.write('LINK:      {}\n'.format(self.link))
        s.write('SUMMARY:   {}\n'.format(self.summary))
        s.write('AVAILABLE: {}\n'.format(self.available_at))
        for b in self.branches:
            s.write(b.to_string())
        return s.getvalue()

class PLSearch(object):
    """Get search results from Library Catalogue website."""

    title = ''
    author = ''
    libservice = ''
    catalogue_url = ''
    search_url = ''
    items_found = [] # a list of SearchResultItem
    error_messages = []

    def run_search(self, libservice, title='', author=''):
        self.libservice = libservice
        backend = get_backend(self.libservice)
        self.catalogue_url = backend.get_catalogue_url(self.libservice);
        self.title = title
        self.author = author

        if not (title or author):
            log_error('PLSearch: must supply title and/or author\n')
            return

        self.search_url = backend.build_search_url(self.catalogue_url, self.title, self.author)

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
        self.items_found = backend.get_search_results(html)

class PrismBackend(object):
    """Backend for prism.librarymanagementcloud websites."""

    prism_url = 'https://prism.librarymanagementcloud.co.uk/'

    def get_id(self):
        global backend_id_prism
        return backend_id_prism

    def get_catalogue_url(self, libservice):
        return self.prism_url + libservice + '/'

    def build_search_url(self, catalogue_url, title='', author=''):
        global match_exact
        title_str = ''
        author_str = ''
        if title:
            if match_exact:
                # use quote marks around the title (%22)
                title_str = '+title%3A%28%22' + title.replace(' ', '+') + '%22%29'
            else:
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
                    item.available_at = 'NOT AVAILABLE'
                    div_avail = html.select('div#availability')
                    if div_avail:

                        avail_status = div_avail[0].select('div.status')
                        if avail_status:
                            p_branches = avail_status[0].select('p.branches')
                            if p_branches:
                                item.available_at = p_branches[0].text

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
                cat_item = CatalogueItem()

                prop = row.findAll('span', {'itemprop' : 'serialNumber'})
                if prop:
                    cat_item.barcode = prop[0].text

                # SKU = Stock Keeping Unit?
                prop = row.findAll('span', {'itemprop' : 'sku'})
                if prop:
                    cat_item.shelfmark = prop[0].text

                # get these by just counting the table cells
                n = 0
                for td in row.select('td'):
                    n += 1
                    if n == 3:
                        cat_item.item_type = td.text.strip()
                    elif n == 4:
                        cat_item.status = td.text.strip()

                bri.add_item(cat_item)

        return bri

class LLCSirsidynixBackend(object):
    """Backend for London Libraries Consortium sirsidynix websites."""

    sirsidynix_url = 'https://llc.ent.sirsidynix.net.uk/client/en_GB/'

    def get_id(self):
        global backend_id_llc_sirsidynix
        return backend_id_llc_sirsidynix

    def get_catalogue_url(self, libservice):
        return self.sirsidynix_url + libservice + '/'

    def build_search_url(self, catalogue_url, title='', author=''):
        """
https://llc.ent.sirsidynix.net.uk/client/en_GB/brent/search/results?qu=&qu=TITLE%3Dlullaby+&qu=AUTHOR%3Dslimani+&h=1
"""
        global match_exact
        title_str = ''
        author_str = ''
        if title:
            if match_exact:
                # use quote marks around the title (%22)
                title_str = '&qu=TITLE%3D%22' + title.replace(' ', '+') + '%22'
            else:
                title_str = '&qu=TITLE%3D' + title.replace(' ', '+')
        if author:
            author_str = '&quAUTHOR%3D' + author.replace(' ', '+')
        url = catalogue_url + 'search/results?qu=' + title_str
        if author_str:
            url += '+' + author_str
        url += '+&h=1'
        return url

    def get_search_results(self, html):
        items_found = []
        count = 0
        for search_results_wrapper in html.select('div#results_wrapper'):
            for record in search_results_wrapper.select('div.results_cell'):
                count += 1
                print(f"\nNEXT ITEM ({count}):")
                item = SearchResultItem()

                # id

                
                # title
                div_detail = record.select('div.displayDetailLink')
                if div_detail:
                    a_detail = div_detail[0].select('a')
                    if a_detail:
                        item.title = a_detail[0].text
                
                
                # publisher
                
                # date
                item.publication_date = self.span_div_div_text(record, 'PUBDATE')

                # span_date = record.select('span.PUBDATE')
                # if span_date:
                #     div_date_1 = span_date[0].select('div.PUBDATE')
                #     if div_date_1:
                #         div_date_2 = div_date_1[0].select('div.PUBDATE')
                #         if div_date_2:
                #             item.publication_date = div_date_2[1].text
                        

                # # link
                # div_link = record.select('div.displayDetailLink')
                # if div_link:
                    
                
                # summary
                # available at
                item.available_at = self.span_div_div_text(record, 'PARENT_AVAILABLE')
                
                
                # branches

                # author
                
                # format
                span_format = record.select('span.formatText')
                if span_format:
                    item.item_type = span_format[0].text
                
                # isbn
                
                items_found.append(item)
        return items_found

    def span_div_div_text(self, html, classname):
        val = '???'
        span = html.select('span.' + classname)
        if span:
            div1 = span[0].select('div.' + classname)
            if div1:
                div2 = div1[0].select('div.' + classname)
                if div2:
                    val = div2[1].text
        return val
        


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

def init_backend(backend_id):
    global backends_dict
    if backend_id == backend_id_prism:
        backends_dict[backend_id] = PrismBackend()
    elif backend_id == backend_id_llc_sirsidynix:
        backends_dict[backend_id] = LLCSirsidynixBackend()

def get_backend(libservice):
    global backends_dict
    global library_service_backends
    global config_filename
    if libservice in library_service_backends:
        b = library_service_backends[libservice]
        if b in backends_dict:
            return backends_dict[b]
        else:
            init_backend(b)
            return backends_dict[b]
    else:
        log_error(f'ERROR: backend for library service "{libservice}" needs to be specified in config file.')
        exit(1)

def do_search(libservice, title, author):
    print(f'\nSEARCHING: library-service="{libservice}", title="{title}", author="{author}"\n')
    search = PLSearch()
    search.run_search(libservice, title=title, author=author)
    show_search(search)
    return search

def do_search_from_file(filename):
    print('\nDO SEARCH FROM FILE: \n'.format(filename))
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
                # 1: a parameter name ([l]ibraryservice, [a]uthor, [t]itle)
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
                        search.run_search(libservice, title=title, author=author)
                        search_results = search_results + [search]
                        show_search(search)

                    else:
                        log_error(f'ERROR in do_search_from_file: parameter "{param}" not recognised.')

    return search_results

def write_output_file_html(results, output_filename):
    """Presents the results nicely in an HTML file.

Arguments:
    results -- a list of PLSearch objects
"""
    fname = output_filename.split(".")[0] + ".html"
    print(f"\n... writing results to file: {fname}...\n\n")
    libservice = ""
    with open(fname, 'w') as f:
        f.write("<!DOCTYPE html>\n")
        f.write("<html>\n")
        f.write("<head>\n")
        f.write("<title>PLScrape: Search Results</title>\n")
        f.write("</head>\n")
        f.write("<body>\n")
        dt = datetime.now()
        dt_str = dt.strftime("%A, %d. %B %Y, %I:%M%p")
        f.write(f"<p>TIME: {dt_str}</p>")
        for search in results:
            if search.libservice != libservice:
                f.write(f'<h1>LIBRARY SERVICE: {search.libservice}')
                libservice = search.libservice
            f.write("<h2>TITLE: {}, AUTHOR: {}</h2>\n".format(search.title, search.author))
            f.write(f'<p>SEARCH URL: <a href="{search.search_url}">{search.search_url}</a></p>')

            # number of records found
            if len(search.items_found) == 1:
                f.write("<p>1 record found</p>")
            else:
                f.write(f"<p>{len(search.items_found)} records found</p>")

            if len(search.items_found) > 0:
                f.write("<ol>")
                for item in search.items_found:
                    f.write(f'<li><b>{item.title}</b>, {item.publication_date}, {item.available_at}')
                    if len(item.branches) > 0:
                        f.write("<ul>")
                        for branch_item in item.branches:

                            f.write(f"<li>{branch_item.name} (")
                            if branch_item.is_available():
                                f.write(f'<span style="color:green"><b>AVAILABLE</b></span>')
                            else:
                                f.write(f'<span style="color:red"><b>UNAVAILABLE</b></span>')
                            f.write('): ')

                            if len(branch_item.items) == 1:
                                f.write(f'{branch_item.items[0].to_string()}</li>')
                            else:
                                f.write('<ul>')
                                for cat_item in branch_item.items:
                                    f.write(f'<li>{cat_item.to_string()}</li>')
                                f.write('</ul>')
                                f.write(f"</li>")

                        f.write("</ul>")
                    f.write("</li>")
                f.write("</ol>")
        f.write("</body>\n")
        f.write("</html>\n")

def discover_catalogue(libservice, site_backends):
    site_engine_for_libservice = ""
    report = []
    # try each site engine in turn
    for engine in site_backends:
        catalogue_url = engine.get_catalogue_url(libservice)
        print(f"trying {catalogue_url}")
        try:
            with closing(get(catalogue_url, stream=True)) as resp:
                print(f"got url: {resp.url}")

                if resp.status_code == 200: # ok
                    if libservice in resp.url:
                        report.append(f"SUCCESS: {resp.url}")
                        site_engine_for_libservice = engine.get_name()
                    else:
                        report.append(f"FAILED: redirected to {resp.url}")
                else:
                    report.append(f"FAILED: HTTP CODE {resp.status_code} {resp.url}")

                if resp.history:
                    print("REDIRECTED...")
                    for step in resp.history:
                        print(f"... CODE={step.status_code} URL={step.url}")

        except RequestException as e:
            log_error(f'Error during requests to {catalogue_url} : {e}')
            report.append(f"FAILED WITH ERROR: {catalogue_url}")


    print(f"\nDISCOVER CATALOGUE WEBSITE FOR {libservice}:")
    for line in report:
        print(line)
    print(f"USE SITE-ENGINE: {site_engine_for_libservice}")
    return site_engine_for_libservice

def discover_catalogue_from_file(filename, site_backends):
    results = []
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip().lower()
            line = "-".join(line.split())
            # ignore empty lines and comments
            if line == "" or line[0] == "#":
                pass
            else:
                engine_id = discover_catalogue(line, site_backends)
                results.append(line + ', ' + engine_id)
    print("\nRESULTS:")
    for r in results:
        print(r)

def load_config(filename):
    global library_service_backends
    print(f"loading config from file: {filename}")
    count = 0
    num_invalid = 0
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip().lower()
            # ignore empty lines and comments
            if line == "" or line[0] == "#":
                pass
            else:
                # get rid of trailing comments
                line = line.split('#')[0].strip()
                # get key/value pair
                parts = line.split(',')
                valid_entry = False
                if len(parts) == 2:
                    k = parts[0].strip()
                    v = parts[1].strip()
                    if v:
                        library_service_backends[k] = v
                        valid_entry = True
                if valid_entry:
                    count += 1
                else:
                    num_invalid += 1
    print(f"loaded config ({count} library services/{num_invalid} invalid entries):")
    for k in library_service_backends.keys():
        print(f"... {k} ---> {library_service_backends[k]}")

if __name__ == '__main__':
    #global config_filename
    # default values for command line args
    discover = ""
    input_filename = ""
    libservice = ""
    author = ""
    title = ""
    output_filename = "output"
    # using argparse to get the command line args
    parser = argparse.ArgumentParser(description='Search Islington Library Catalogue')
    parser.add_argument('--discover', '-d', metavar='D', type=str, nargs=1)
    parser.add_argument('--filename', '-f', metavar='F', type=str, nargs=1)
    parser.add_argument('--libservice', '-l', metavar='L', type=str, nargs=1)
    parser.add_argument('--author', '-a', metavar='A', type=str, nargs=1)
    parser.add_argument('--title', '-t', metavar='T', type=str, nargs=1)
    parser.add_argument('--output', '-o', metavar='O', type=str, nargs=1)
    args = parser.parse_args()
    # argparse gets the args as lists - just want first element
    if args.discover:
        discover = args.discover[0]
    if args.filename:
        input_filename = args.filename[0]
    if args.libservice:
        libservice = args.libservice[0]
    if args.author:
        author = args.author[0]
    if args.title:
        title = args.title[0]
    if args.output:
        output_filename = args.output[0]

    # load config file
    # note 'global' not required in main to access global variable 'config_filename'
    load_config(config_filename)

    # discover-mode takes priority
    if discover:
        site_backends = [PrismBackend(),
                         LLCSirsidynixBackend()]
        if input_filename:
            discover_catalogue_from_file(input_filename, site_backends)
        else:
            discover_catalogue(discover, site_backends)

    else:

        results = []

        if input_filename:
            results = do_search_from_file(input_filename)
        else:
            if not libservice:
                print("Please specify the library service to search, or provide an input file.")
                exit(1)
            if not (title or author):
                print("Please specify a title and/or an author.")
                exit(1)
            search = do_search(libservice, title, author)
            results = [search]

        write_output_file_html(results, output_filename)
