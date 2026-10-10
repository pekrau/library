"NiceGUI-based interface to library data."

__version__ = "0.0.1"

import calendar
import datetime
import os
import pathlib
import re
import string
import sys
import unicodedata

import bibtexparser
import dotenv
from nicegui import ui
import yaml

dotenv.load_dotenv()

FILENAME_CHARACTERS = set(string.ascii_letters + string.digits + "-")
FRONTMATTER = re.compile(r"^---([\n\r].*?[\n\r])---[\n\r](.*)$", re.DOTALL)

MONTHS = dict(
    [(name.lower(), number) for number, name in enumerate(calendar.month_name[1:])]
)
MONTHS.update(
    dict(
        [(name.lower(), number) for number, name in enumerate(calendar.month_abbr[1:])]
    )
)


def normalize(s):
    "Normalize string to ASCII, fold case, replace non-file characters with '-'."
    result = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore")
    result = "".join(
        [c if c in FILENAME_CHARACTERS else "-" for c in result.decode("utf-8")]
    )
    return result.casefold()


def header(title, color="green", edit=None, delete=None):
    with ui.header().classes(f"text-h5 bg-{color}-500"):
        with ui.button(icon="menu").props("color=dark"):
            with ui.menu():
                ui.menu_item("Home", lambda: ui.navigate.to("/"))
                if edit:
                    ui.menu_item("Edit", lambda: ui.navigate.to(edit))
                if delete:
                    ui.menu_item("Delete", lambda: ui.navigate.to(delete))
                ui.menu_item("Add BibTex", lambda: ui.navigate.to("/bibtex"))
                ui.menu_item("Add article", lambda: ui.navigate.to("/article"))
                ui.menu_item("Add book", lambda: ui.navigate.to("/book"))
        ui.label(title)


def items_table(items):
    ui.table(
        columns=[
            dict(name="reference", label="Reference", field="reference", align="left"),
            dict(name="title", label="Title", field="title", align="left"),
            dict(name="authors", label="Authors", field="authors", align="left"),
            dict(name="year", label="Year", field="year", align="left"),
        ],
        rows=[
            dict(
                reference=i.reference,
                title=i.title,
                authors="; ".join(i.authors),
                year=i.year,
                url=i.url,
            )
            for i in items
        ],
        row_key="name",
    ).props("bordered").on(
        "row-click", lambda e: ui.navigate.to(e.args[1]["url"], new_tab=True)
    )


class Library:

    def __init__(self):
        self.root_dir = pathlib.Path(os.environ["LIBRARY_DIR"])
        self.trash_dir = self.root_dir / "trash"
        self.items = {}

    def __contains__(self, reference):
        return normalize(reference) in self.items

    def __getitem__(self, reference):
        return self.items[normalize(reference)]

    def __call__(self):
        return sorted(self.items.values(), key=lambda i: i.modified)

    def read(self, filepath=os.environ["LIBRARY_DIR"]):
        "Read all items in the library data directory."
        self.items.clear()
        for filename in pathlib.Path(filepath).glob("*.md"):
            content = pathlib.Path(filename).read_text()
            m = FRONTMATTER.match(content)
            if not m:
                raise ValueError
            frontmatter = yaml.safe_load(m.group(1))
            match frontmatter["type"]:
                case "article":
                    item = Article(frontmatter, content[m.start(2) :])
                case "book":
                    item = Book(frontmatter, content[m.start(2) :])
                case _:
                    sys.exit(f"Error: type-less item '{filename}'")
            self.items[item.identifier] = item

    def parse_bibtex(self, text):
        "Parse the items in the BibTex source text and add to the library."
        result = []
        for entry in bibtexparser.parse_string(text).entries:
            match entry.entry_type:
                case "article":
                    item = Article()
                case "book":
                    item = Book()
                case _:
                    raise ValueError(f"cannot handle BibTex type '{entry.entry_type}'")
            item.from_bibtex(dict([(f.key, f.value) for f in entry.fields]))
            # Construct the reference and insert into library
            base_reference = f"{item.authors[0].split(',')[0].strip()} {item.year}"
            reference = base_reference
            letters = list(string.ascii_lowercase)
            while reference in self:
                reference = base_reference + letters.pop(0)
            item.reference = reference
            item.write()
            result.append(item)
        return result


class Item:

    def __init__(self, frontmatter=None, text=None):
        self.frontmatter = frontmatter or {"type": self.type, "authors": []}
        self.text = text or ""

    @property
    def type(self):
        return self.__class__.__name__.lower()

    @property
    def reference(self):
        return self.frontmatter.get("reference") or ""

    @reference.setter
    def reference(self, new):
        global library
        if not new:
            raise ValueError("null reference")
        if new == self.reference:
            return
        if new in library:
            raise ValueError("reference already exists in library")
        if self.identifier:
            library.items.pop(self.identifier)
            self.filepath.rename(library.trash_dir / self.filename)
        self.frontmatter["reference"] = new
        library.items[self.identifier] = self

    @property
    def identifier(self):
        return normalize(self.reference)

    @property
    def filename(self):
        return f"{self.identifier}.md"

    @property
    def filepath(self):
        return library.root_dir / self.filename

    @property
    def modified(self):
        return datetime.datetime.fromtimestamp((self.filepath.stat().st_mtime))

    @property
    def title(self):
        return self.frontmatter.get("title") or ""

    @property
    def authors(self):
        return self.frontmatter.get("authors") or []

    @property
    def published(self):
        return self.frontmatter.get("published") or ""

    @property
    def year(self):
        return self.frontmatter.get("year") or ""

    @property
    def pages(self):
        return self.frontmatter.get("pages") or ""

    @property
    def doi(self):
        return self.frontmatter.get("doi") or ""

    @property
    def pmid(self):
        return self.frontmatter.get("pmid") or ""

    @property
    def url(self):
        return f"/view/{self.identifier}"

    def from_bibtex(self, fields):
        assert not self.reference
        global library
        self.frontmatter["title"] = fields["title"]
        self.frontmatter["authors"] = fields["author"].split(" and ")
        self.frontmatter["year"] = fields["year"]
        # 'month' to 'published'
        month = fields.get("month", "")
        parts = month.split("#")
        if len(parts) == 2 and parts[1]:
            month = MONTHS[parts[1].strip().casefold()]
            day = int("".join([c for c in parts[0] if c in string.digits]))
            self.frontmatter["published"] = f'{fields["year"]}-{month:02d}-{day:02d}'
        elif len(parts) == 1 and parts[0]:
            month = MONTHS[parts[0].strip().casefold()]
            self.frontmatter["published"] = f'{fields["year"]}-{month:02d}-01'
        try:
            self.frontmatter["publisher"] = fields["publisher"]
        except KeyError:
            pass
        try:
            self.frontmatter["pages"] = fields["pages"].replace("--", "-")
        except KeyError:
            pass
        for key in ["publisher", "address", "number", "doi"]:
            try:
                self.frontmatter[key] = fields[key]
            except KeyError:
                pass
        self.text = fields.get("abstract", "")

    def view(self):
        header(
            self.reference,
            color=self.COLOR,
            edit=f"/edit/{self.identifier}",
            delete=f"/delete/{self.identifier}",
        )
        ui.label(self.title).classes("text-h5")
        with ui.row():
            for author in self.authors:
                ui.label(author)

    def edit(self):
        if self.reference:
            header(f"Edit {self.type}", color=self.COLOR)
        else:
            header(f"Add {self.type}", color=self.COLOR)
        self.reference_field = ui.input("Reference", value=self.reference)
        self.title_field = ui.input("Title", value=self.title).classes("w-200")
        self.authors_field = ui.textarea(
            "Authors", value="\n".join(self.authors)
        ).classes("w-64")
        self.published_field = ui.date_input("Published", value=self.published)
        if self.reference:
            ui.button("Save", on_click=self.save)
            ui.button("Cancel", on_click=lambda: ui.navigate.to(self.url)).classes(
                "!bg-gray-500"
            )
        else:
            ui.button("Add", on_click=self.save)

    def save(self):
        try:
            self.reference = self.reference_field.value
            self.frontmatter["title"] = self.title_field.value.strip() or "no title"
            self.frontmatter["authors"] = self.authors_field.value.split("\n")
            published = self.published_field.value
            self.frontmatter["published"] = published
            self.frontmatter["year"] = published.split("-")[0]
        except (ValueError, TypeError, IndexError) as error:
            ui.button(
                f"Error: {error}", type="negative", position="center", close_button="OK"
            )
            return
        self.write()
        ui.navigate.to(self.url)

    def write(self):
        with self.filepath.open(mode="w", encoding="utf-8") as outfile:
            outfile.write("---\n")
            outfile.write(yaml.safe_dump(self.frontmatter, allow_unicode=True))
            outfile.write("---\n")
            if self.text:
                outfile.write(self.text)

    def confirm_delete(self):
        header(f"Delete {self.reference} ?", color="red")
        ui.label("Really delete this item?").classes("text-h4")
        ui.button("Yes", on_click=self.delete).props("color=negative")
        ui.button("Cancel", on_click=lambda: ui.navigate.to(self.url)).classes(
            "!bg-gray-500"
        )

    def delete(self):
        library.items.pop(self.identifier)
        self.filepath.rename(library.trash_dir / self.filename)
        ui.navigate.to("/")


class Article(Item):

    COLOR = "blue"

    @property
    def journal(self):
        return self.frontmatter.get("journal") or ""

    @property
    def volume(self):
        return self.frontmatter.get("volume") or ""

    @property
    def issue(self):
        return self.frontmatter.get("issue") or ""

    def from_bibtex(self, fields):
        super().from_bibtex(fields)
        for key in ["journal", "issn", "volume", "pmid", "pmc"]:
            try:
                self.frontmatter[key] = fields[key]
            except KeyError:
                pass

    def view(self):
        super().view()
        with ui.row():
            ui.label(self.journal or "-")
            ui.label(self.volume or "-").classes("text-weight-bold")
            if self.issue:
                ui.label(f"({self.issue})")
            ui.label(self.pages or "-")
            ui.label(self.published)
        with ui.row():
            if self.doi:
                ui.link(self.doi, f"https://doi.org/{self.doi}", new_tab=True)
            if self.pmid:
                ui.link(
                    f"PubMed {self.pmid}",
                    f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/",
                    new_tab=True,
                )
        ui.markdown(self.text).classes("w-200")


class Book(Item):

    COLOR = "purple"

    @property
    def publisher(self):
        return self.frontmatter.get("publisher") or ""

    @property
    def isbn(self):
        return self.frontmatter.get("isbn") or ""

    def from_bibtex(self, fields):
        super().from_bibtex(fields)
        for key in ["series", "isbn"]:
            try:
                self.frontmatter[key] = fields[key]
            except KeyError:
                pass

    def view(self):
        super().view()
        with ui.row():
            ui.label(self.publisher or "-")
            ui.label(self.published)
        with ui.row():
            if self.doi:
                ui.link(f"DOI {self.doi}", f"https://doi.org/{self.doi}", new_tab=True)
            if self.isbn:
                ui.link(
                    f"ISBN {self.isbn}",
                    f"https://isbnsearch.org/isbn/{self.isbn}",
                    new_tab=True,
                )
        ui.markdown(self.text).classes("w-200")


library = Library()
library.read()


@ui.page("/view/{identifier}")
def view_item_page(identifier: str):
    global library
    item = library[identifier]
    item.view()


@ui.page("/edit/{identifier}")
def edit_item_page(identifier: str):
    global library
    item = library[identifier]
    item.edit()


@ui.page("/delete/{identifier}")
def delete_item_page(identifier: str):
    global library
    item = library[identifier]
    item.confirm_delete()


@ui.page("/bibtex")
def add_bibtex():
    global library
    header(f"Add bibtex", color="yellow")
    textarea = ui.textarea(label="BibTex source").classes("w-100")

    def show_items(items):
        items_table(items)
        textarea.value = ""

    ui.button(
        "Parse", on_click=lambda: show_items(library.parse_bibtex(textarea.value))
    )
    ui.button("Cancel", on_click=lambda: ui.navigate.to("/").classes("!bg-gray-500"))


@ui.page("/article")
def add_article_page():
    Article().edit()


@ui.page("/book")
def add_book_page():
    Book().edit()


@ui.page("/")
def main():
    global library
    header(f"Library v{__version__}")
    items_table(library())


ui.run(title="Library")
