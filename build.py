"Build the 'docs' contents from the latest CSV file from Goodreads."

__version__ = '0.1.0'

import collections
import csv
import json
import os
import os.path
import string

import jinja2

GOODREADS_PATH     = os.path.expanduser('~/Dropbox/archive/goodreads')
DOCS_PATH          = os.path.join(os.getcwd(), 'docs')
CORRECTIONS_PATH   = os.path.join(os.getcwd(), 'corrections')
TEMPLATES_PATH     = os.path.join(os.getcwd(), 'templates')
GOODREADS_URL_BASE = 'https://www.goodreads.com/book/show/'

BOOKID_COL      = 0
TITLE_COL       = 1
AUTHOR_COL      = 3
ADDAUTHORS_COL  = 4
BOOKSHELVES_COL = 16
EXBOOKSHELF_COL = 18
ISBN_COL        = 5
ISBN13_COL      = 6
RATING_COL      = 7
PUBLISHED_COL   = 12
ORIGPUBL_COL    = 13
DATEREAD_COL    = 14
REVIEW_COL      = 19

Book = collections.namedtuple('Book', ['id', 'title', 'author1', 'author',
                                       'authors', 'isbn', 'isbn13', 'rating',
                                       'average_rating', 'publisher',
                                       'binding', 'pages', 'ed_published',
                                       'published', 'read', 'added',
                                       'bookshelves', 'bookshelves_pos',
                                       'exshelf', 'review', 'spoiler',
                                       'notes', 'read_count', 'recommended_for',
                                       'recommended_by', 'copies',
                                       'purchase_date', 'purchase_location',
                                       'condition', 'condition_description',
                                       'ref'])

# Source file: latest CSV dump from Goodreads.
filename = sorted(os.listdir(GOODREADS_PATH))[-1]
filepath = os.path.join(GOODREADS_PATH, filename)
with open(filepath) as infile:
    reader = csv.reader(infile)
    header = next(reader)
    books = list(map(Book._make, reader))
print(filename, len(books), 'books')

# Fix up fields 'authors', 'isbn', 'isbn13', 'bookshelves', 'published'.
for pos, book in enumerate(books):
    parts = [s.strip() for s in book.author.split(',')]
    authors = [(parts[0], ' '.join(parts[1:]))]
    for name in book.authors.split(','):
        name = name.strip()
        if not name: continue
        parts = name.split()
        authors.append((parts[-1], ' '.join(parts[:-1])))
    bookshelves = set(s.strip() for s in book.bookshelves.split(','))
    bookshelves.difference_update([book.exshelf])
    books[pos] = book._replace(authors=authors,
                               isbn=''.join([c for c in book.isbn
                                             if c in string.digits]),
                               isbn13=''.join([c for c in book.isbn13
                                               if c in string.digits]),
                               bookshelves=bookshelves,
                               published=book.published or book.ed_published)

# Lookup from book id to pos in list 'books'.
id_lookup_pos = {}
for pos, book in enumerate(books):
    id_lookup_pos[book.id] = pos

# Read the correction files, if any.
for corrname in os.listdir(CORRECTIONS_PATH):
    if not corrname.endswith('.json'): continue
    id = corrname[:-5]
    with open(os.path.join(CORRECTIONS_PATH, corrname)) as infile:
        data = json.load(infile)
    books[id_lookup_pos[id]] = books[id_lookup_pos[id]]._replace(**data)

# Determine ref "{first_author_family_name} {published}" for each book.
refs = {}
for book in books:
    if book.ref:                # If already set by a corrections file.
        ref = book.ref
    else:
        ref = f"{book.authors[0][0]} {book.published}"
    refs.setdefault(ref, []).append(book)

for ref, ref_books in refs.items():
    if len(ref_books) > 1:
        ref_books.sort(key=lambda b: b.title)
        for number, book in enumerate(ref_books):
            ordinal = string.ascii_lowercase[number]
            books[id_lookup_pos[book.id]] = book._replace(ref=f"{ref}{ordinal}")
    else:
        book = ref_books[0]
        books[id_lookup_pos[book.id]] = book._replace(ref=ref)

# Find all bookshelves.
bookshelves = set()
for book in books:
    bookshelves.update(book.bookshelves)
bookshelves = sorted(bookshelves)

# Find all alphabeticals for authors.
alphabetical = set()
for book in books:
    for author in book.authors:
        alphabetical.add(author[0][0].upper())
alphabetical = sorted(alphabetical)

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES_PATH),
    autoescape=jinja2.select_autoescape(['html'])
)
env.globals['len'] = len
env.globals['sorted'] = sorted
env.globals['enumerate'] = enumerate
env.globals['format_authors'] = lambda authors: '; '.join([f"{a[0]}, {a[1]}" for a in authors])
env.globals['url_base'] = ''
env.globals['goodreads_url_base'] = GOODREADS_URL_BASE
env.globals['source'] = filename
env.globals['total_books'] = len(books)
env.globals['bookshelves'] = bookshelves

@jinja2.environmentfilter
def author_link(env, author):
    name = f"{author[0]}, {author[1]}"
    filename = f"{author[0]} {author[1]}.html".replace(' ', '-')
    href = f"{env.globals['url_base']}authors/{filename}"
    return jinja2.Markup(f'<a href="{href}">{name}</a>')
env.filters['author_link'] = author_link

# Record all files written in this run.
written = set()

# Home page.
template = env.get_template('index.html')
path = os.path.join(DOCS_PATH, 'index.html')
with open(path, 'w') as outfile:
    outfile.write(template.render(alphabetical=alphabetical))
written.add(path)

# Books subdirectory and book pages.
path = os.path.join(DOCS_PATH, 'books')
if not os.path.exists(path): os.mkdir(path)
written.add(path)

template = env.get_template('book.html')
for book in books:
    path = os.path.join(DOCS_PATH, 'books', book.ref.replace(' ', '-'))
    path += '.html'
    with open(path, 'w') as outfile:
        outfile.write(template.render(url_base='../',
                                      page_title=book.ref,
                                      book=book))
    written.add(path)

# All books page.
template = env.get_template('list.html')
path = os.path.join(DOCS_PATH, 'all.html')
with open(path, 'w') as outfile:
    outfile.write(template.render(page_title='All books',
                                  books=sorted(books, key=lambda b: b.ref)))
written.add(path)

# Bookshelf pages.
template = env.get_template('list.html')
for bookshelf in bookshelves:
    path = os.path.join(DOCS_PATH, f"{bookshelf}.html")
    with open(path, 'w') as outfile:
        outfile.write(
            template.render(
                page_title=f"Bookshelf {bookshelf.replace('-', ' ')}",
                books=sorted([b for b in books if bookshelf in b.bookshelves],
                             key=lambda b: b.ref)))
    written.add(path)

# Authors subdirectory and author pages.
path = os.path.join(DOCS_PATH, 'authors')
if not os.path.exists(path): os.mkdir(path)
written.add(path)

authors = set()
author_lookup_books = {}
for book in books:
    authors.update(book.authors)
    for author in book.authors:
        author_lookup_books.setdefault(author, []).append(book)

for author, books in author_lookup_books.items():
    filename = f"{author[0]} {author[1]}.html".replace(' ', '-')
    path = os.path.join(DOCS_PATH, 'authors', filename)
    with open(path, 'w') as outfile:
        outfile.write(
            template.render(
                page_title=f"{author[0]}, {author[1]}",
                books=sorted(books, key=lambda b: b.ref)))
    written.add(path)

# Author lists by first letter of family name.
char_lookup_authors = {}
for author in authors:
    char = author[0][0].upper()
    char_lookup_authors.setdefault(char, []).append(author)


print(len(written), 'files written')
