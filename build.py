"Build the 'docs' contents from the latest CSV file from Goodreads."

__version__ = '0.0.1'

import csv
import os
import os.path

import jinja2

GOODREADS_PATH = os.path.expanduser('~/Dropbox/archive/goodreads')
DOCS_PATH = os.path.join(os.getcwd(), 'docs')
TEMPLATES_PATH = os.path.join(os.getcwd(), 'templates')

filenames = sorted(os.listdir(GOODREADS_PATH))
filepath = os.path.join(GOODREADS_PATH, filenames[-1])
print('reading', filepath)

with open(filepath) as infile:
    reader = csv.reader(infile)
    header = next(reader)
    rows = list(reader)

print(len(rows), 'books')

bookshelves_col = None
for pos, item in enumerate(header):
    if item == 'Bookshelves':
        bookshelves_col = pos
        break
else:
    raise ValueError("Error: could not find the 'Bookshelves' column")
exbookshelf_col = None
for pos, item in enumerate(header):
    if item == 'Exclusive Shelf':
        exbookshelf_col = pos
        break
else:
    raise ValueError("Error: could not find the 'Exclusive Shelf' column")

bookshelves = set()
exbookshelf = set()
for row in rows:
    bookshelves.update([s.strip() for s in row[bookshelves_col].split(',')])
    exbookshelf.update([s.strip() for s in row[exbookshelf_col].split(',')])
tags = list(bookshelves.difference(exbookshelf))

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES_PATH),
    autoescape=jinja2.select_autoescape(['html'])
)

with open(os.path.join(DOCS_PATH, 'index.html'), 'w') as outfile:
    template = env.get_template('index.html')
    outfile.write(template.render(tags=tags))