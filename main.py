"NiceGUI-based interface to library data."

__version__ = "0.3.1"

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

MAX_ROWS = 40
FILENAME_CHARACTERS = set(string.ascii_letters + string.digits + "-")
FRONTMATTER = re.compile(r"^---([\n\r].*?[\n\r])---[\n\r](.*)$", re.DOTALL)

MONTHS = dict(
    [(name.lower(), number + 1) for number, name in enumerate(calendar.month_name[1:])]
)
MONTHS.update(
    dict(
        [
            (name.lower(), number + 1)
            for number, name in enumerate(calendar.month_abbr[1:])
        ]
    )
)


def normalize(s):
    "Normalize string to ASCII, fold case, replace non-file characters with '-'."
    result = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore")
    result = "".join(
        [c if c in FILENAME_CHARACTERS else "-" for c in result.decode("utf-8")]
    )
    return result.casefold()


class Library:

    def __init__(self):
        self.root_dir = pathlib.Path(os.environ["LIBRARY_DIR"])
        self.trash_dir = self.root_dir / "trash"
        self.items = {}  # Key: identifier (normalized reference), value: instance.
        self.configfilepath = self.root_dir / "config.yaml"
        self.tags = []

    def __contains__(self, reference):
        return normalize(reference) in self.items

    def __getitem__(self, reference):
        return self.items[normalize(reference)]

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
        if self.configfilepath.exists():
            config = yaml.safe_load(self.configfilepath.read_text())
            self.tags = config.get("tags", [])

    def add_tag(self, tag):
        tags = set(self.tags)
        tags.add(tag)
        self.tags = sorted(tags, key=lambda t: t.casefold())

    def delete_tag(self, tag):
        try:
            self.tags.remove(tag)
        except ValueError:
            return
        self.write_tags()
        # Delete the tag from all items.
        for item in self.items.values():
            try:
                item.frontmatter.get("tags", []).remove(tag)
            except ValueError:
                pass
            else:
                item.write()

    def write_tags(self):
        with self.configfilepath.open(mode="w", encoding="utf-8") as outfile:
            outfile.write(yaml.safe_dump(dict(tags=self.tags), allow_unicode=True))

    def get_tag(self, value):
        for tag in self.tags:
            if tag == value:
                return tag
            elif normalize(tag) == value:
                return tag
        return None

    def count_tagged_items(self, tag):
        return len([i for i in self.items.values() if tag in i.tags])

    def parse_bibtex(self, text):
        """Parse the items in the BibTex source text.
        Add to the library.
        If single item, redirect to its page.
        If multiple items, redirect to the home page, where the most recent
        items will be shown.
        """
        items = []
        for entry in bibtexparser.parse_string(text).entries:
            match entry.entry_type:
                case "article":
                    item = Article()
                case "book":
                    item = Book()
                case _:
                    raise ValueError(f"cannot handle BibTex type '{entry.entry_type}'")
            item.from_bibtex(dict([(f.key, f.value) for f in entry.fields]))
            # Set the reference, which adds it to the library.
            if item.authors:
                author = item.authors[0]
            else:
                author = "Anonymous"
            base_reference = f"{author.split(',')[0].strip()} {item.year}"
            reference = base_reference
            letters = list(string.ascii_lowercase)
            # Until reference is unique.
            while reference in self:
                reference = base_reference + letters.pop(0)
            item.reference = reference
            item.write()
            items.append(item)
        if len(items) == 1:
            ui.navigate.to(items[0].view_url)
        elif items:
            ui.navigate.to("/")
        else:
            ui.notify("No items found", type="warning", position="center")

    def table_setup(self, title="", author="", year="", tags=None, text=""):
        with ui.row(align_items="baseline"):
            self.title_filter = ui.input(label="Title", value=title)
            self.author_filter = ui.input(label="Author", value=author)
            self.year_filter = ui.input(label="Year", value=year)
            self.tags_filter = (
                ui.select(library.tags, label="Tags", multiple=True, value=tags)
                .classes("w-80")
                .props("use-chips")
            )
            self.text_filter = ui.input(label="Text", value=text)
            ui.button("Filter", on_click=lambda: self.table_refresh())
            ui.button("Clear", on_click=lambda: self.table_inputs_clear())
        self.table(title=title, author=author, year=year, tags=tags, text=text)

    def table_refresh(self):
        args = dict()
        args["title"] = self.title_filter.value.strip()
        args["author"] = self.author_filter.value.strip()
        args["year"] = self.year_filter.value.strip()
        args["tags"] = self.tags_filter.value
        args["text"] = self.text_filter.value.strip()
        self.table.refresh(**args)

    def table_inputs_clear(self):
        self.title_filter.set_value("")
        self.author_filter.set_value("")
        self.year_filter.set_value("")
        self.tags_filter.set_value(None)
        self.text_filter.set_value("")
        self.table_refresh()

    @ui.refreshable
    def table(self, title=None, author=None, year=None, tags=None, text=None):
        items = self.items.values()
        if title:
            title = title.casefold()
            items = [i for i in items if title in i.title.casefold()]
        if author:
            author = author.casefold()
            items = [
                i for i in items if author in "\n".join(i.authors_short).casefold()
            ]
        if year:
            items = [i for i in items if i.year.startswith(year)]
        if tags:
            tags = set(tags)
            items = [i for i in items if not tags.difference(set(i.tags))]
        if text:
            text = text.casefold()
            items = [i for i in items if text in i.text.casefold()]
        items = list(sorted(items, key=lambda i: i.modified, reverse=True))
        total = len(items)
        items = items[:MAX_ROWS]
        ui.table(
            columns=[
                dict(
                    name="reference", label="Reference", field="reference", align="left"
                ),
                dict(
                    name="title",
                    label="Title",
                    field="title",
                    align="left",
                    style="text-wrap: wrap",
                ),
                dict(
                    name="authors",
                    label="Authors",
                    field="authors",
                    align="left",
                    style="text-wrap: wrap",
                ),
                dict(name="tags", label="Tags", field="tags", align="left"),
                dict(name="year", label="Year", field="year", align="left"),
            ],
            rows=[
                dict(
                    reference=i.reference,
                    title=i.title,
                    authors="; ".join(i.authors_short),
                    year=i.year,
                    tags=", ".join(i.tags),
                    url=i.view_url,
                )
                for i in items
            ],
            row_key="name",
        ).props("bordered").on("row-click", lambda e: ui.navigate.to(e.args[1]["url"]))
        with ui.row():
            if total > len(items):
                ui.label(f"{len(items)} items shown,").classes("text-bold")
            ui.label(f"{total} items found,")
            ui.label(f"{len(library.items)} total items.")


class Item:

    def __init__(self, frontmatter=None, text=None):
        self.frontmatter = frontmatter or {"type": self.type}
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
        return datetime.datetime.fromtimestamp(
            (self.filepath.stat().st_mtime)
        ).strftime("%Y-%m-%d %H:%M:%S")

    @property
    def title(self):
        return self.frontmatter.get("title", "")

    @title.setter
    def title(self, value):
        self.set_key_value("title", value)

    def set_key_value(self, key, value):
        if value := value.strip():
            self.frontmatter[key] = value
        else:
            self.frontmatter.pop(key, None)

    @property
    def authors(self):
        return self.frontmatter.get("authors", [])

    @authors.setter
    def authors(self, value):
        if isinstance(value, str):
            value = value.split("\n")
        elif not isinstance(value, list):
            raise ValueError
        value = [v.strip() for v in value]
        if value := [v for v in value if v]:
            self.frontmatter["authors"] = value
        else:
            self.frontmatter.pop("authors", None)

    @property
    def authors_short(self):
        authors = self.authors
        if len(authors) > 7:
            authors = authors[:3] + ["..."] + authors[-2:]
        return authors

    @property
    def year(self):
        return self.frontmatter.get("year", "")

    @year.setter
    def year(self, value):
        value = value.strip()
        if not value:
            raise ValueError("no value given for 'year'")
        self.frontmatter["year"] = value

    @property
    def tags(self):
        return self.frontmatter.get("tags", [])

    @tags.setter
    def tags(self, value):
        if value:
            if isinstance(value, str):
                value = [v.strip() for v in value.split(",")]
            if not isinstance(value, list):
                raise ValueError
            value = [v for v in value if v]
        if value:
            self.frontmatter["tags"] = sorted(value, key=lambda t: t.casefold())
        else:
            self.frontmatter.pop("tags", None)

    @property
    def published(self):
        return self.frontmatter.get("published", "")

    @published.setter
    def published(self, value):
        self.set_key_value("published", value)

    @property
    def number(self):
        return self.frontmatter.get("number") or ""

    @number.setter
    def number(self, value):
        self.set_key_value("number", value)

    @property
    def pages(self):
        return self.frontmatter.get("pages") or ""

    @pages.setter
    def pages(self, value):
        self.set_key_value("pages", value)

    @property
    def doi(self):
        return self.frontmatter.get("doi") or ""

    @doi.setter
    def doi(self, value):
        self.set_key_value("doi", value)

    @property
    def paperpile(self):
        return self.frontmatter.get("paperpile") or ""

    @paperpile.setter
    def paperpile(self, value):
        self.set_key_value("paperpile", value)

    @property
    def publisher(self):
        return self.frontmatter.get("publisher") or ""

    @publisher.setter
    def publisher(self, value):
        self.set_key_value("publisher", value)

    @property
    def address(self):
        return self.frontmatter.get("address") or ""

    @address.setter
    def address(self, value):
        self.set_key_value("address", value)

    @property
    def view_url(self):
        return f"/view/{self.identifier}"

    @property
    def edit_url(self):
        return f"/edit/{self.identifier}"

    @property
    def delete_url(self):
        return f"/delete/{self.identifier}"

    def from_bibtex(self, fields):
        assert not self.reference
        # The first three slots are required.
        self.title = fields["title"]
        self.authors = fields["author"].split(" and ")  # Must be split thus here.
        self.year = fields["year"]
        # Create 'published' from 'year' and 'month'.
        month = fields.get("month", "")
        parts = month.split("#")
        if len(parts) == 2 and parts[1]:
            month = MONTHS[parts[1].strip().casefold()]
            day = int("".join([c for c in parts[0] if c in string.digits]))
            self.frontmatter["published"] = f'{fields["year"]}-{month:02d}-{day:02d}'
        elif len(parts) == 1 and parts[0]:
            month = MONTHS[parts[0].strip().casefold()]
            self.published = f'{fields["year"]}-{month:02d}-01'
        else:
            self.published = fields["year"]
        try:
            self.pages = fields["pages"].replace("--", "-")
        except KeyError:
            pass
        for key in ["number", "doi", "publisher", "address"]:
            try:
                self.set_key_value(key, fields[key])
            except KeyError:
                pass
        self.text = fields.get("abstract", "")

    def view(self):
        with ui.header().classes(f"text-h5"):
            ui.button(icon="home", on_click=lambda: ui.navigate.to("/"))
            ui.label(self.reference)
            ui.button(icon="content_copy").on(
                "click",
                js_handler=f"""
    () => navigator.clipboard.writeText("{self.reference}")
""",
            )
        ui.label(self.title).classes("text-h5")
        with ui.grid(columns="auto auto"):
            ui.label(self.year).classes("text-bold")
            with ui.row():
                for author in self.authors:
                    ui.label(author)
            ui.label("Tags:").classes("text-italic")
            with ui.row():
                for tag in self.tags:
                    ui.link(tag, f"/tag/{normalize(tag)}")
            self.view_additional()
            ui.label("Published:").classes("text-italic")
            with ui.row():
                if self.published:
                    ui.label(self.published)
                if self.publisher:
                    ui.label(self.publisher)
                if self.address:
                    ui.label(self.address)
        with ui.row(align_items="baseline"):
            ui.button("Edit", on_click=lambda: ui.navigate.to(self.edit_url))
            ui.label(self.modified)
            ui.button("Delete", on_click=lambda: ui.navigate.to(self.delete_url)).props(
                "color=negative"
            )
        ui.markdown(self.text).classes("w-200")

    def view_additional(self):
        pass

    def edit(self):
        with ui.header().classes(f"text-h5"):
            ui.button(icon="home", on_click=lambda: ui.navigate.to("/"))
            if self.reference:
                ui.label(f"Edit {self.type}")
            else:
                ui.label(f"Add {self.type}")
        self.reference_field = ui.input(label="Reference", value=self.reference)
        self.title_field = ui.input(label="Title", value=self.title).classes("w-200")
        self.authors_field = ui.textarea(
            label="Authors", value="\n".join(self.authors)
        ).classes("w-64")
        self.tags_field = (
            ui.select(library.tags, label="Tags", multiple=True, value=self.tags)
            .classes("w-100")
            .props("use-chips")
        )
        with ui.row():
            with ui.column():
                self.year_field = ui.input(label="Year", value=self.year)
                self.published_field = ui.date_input(
                    label="Published", value=self.published
                )
                self.publisher_field = ui.input(label="Publisher", value=self.publisher)
                self.address_field = ui.input(label="Address", value=self.address)
            with ui.column():
                self.edit_additional()
            with ui.column():
                self.text_field = ui.textarea("Text", value=self.text).classes("w-200")
        if self.reference:
            with ui.row():
                ui.button("Save", on_click=self.save)
                ui.button(
                    "Cancel", on_click=lambda: ui.navigate.to(self.view_url)
                ).props("color=dark")
        else:
            ui.button("Add", on_click=self.save)

    def edit_additional(self):
        pass

    def save(self):
        try:
            self.reference = self.reference_field.value
            self.title = self.title_field.value
            self.authors = self.authors_field.value
            self.year = self.year_field.value
            self.tags = self.tags_field.value
            published = self.published_field.value.strip()
            if len(published.split("-")) == 2:  # Only year and month given.
                self.published = published + "-01"
            else:
                self.published = published
            self.publisher = self.publisher_field.value
            self.address = self.address_field.value
            self.text = self.text_field.value
            self.save_additional()
        except (ValueError, TypeError, IndexError) as error:
            ui.button(
                f"Error: {error}", type="negative", position="center", close_button="OK"
            )
            return
        self.write()
        ui.navigate.to(self.view_url)

    def save_additional(self):
        pass

    def write(self):
        if self.filepath.exists():
            self.filepath.rename(library.trash_dir / self.filename)
        with self.filepath.open(mode="w", encoding="utf-8") as outfile:
            outfile.write("---\n")
            outfile.write(yaml.safe_dump(self.frontmatter, allow_unicode=True))
            outfile.write("---\n")
            if self.text:
                outfile.write(self.text)

    def confirm_delete(self):
        with ui.header().classes(f"text-h5"):
            ui.button(icon="home", on_click=lambda: ui.navigate.to("/"))
            ui.label("Delete item?")
        ui.label(f"Really delete {self.reference} ?").classes("text-h4")
        with ui.row():
            ui.button("Yes", on_click=self.delete).props("color=negative")
            ui.button("Cancel", on_click=lambda: ui.navigate.to(self.view_url)).props(
                "color=dark"
            )

    def delete(self):
        global library
        library.items.pop(self.identifier)
        self.filepath.rename(library.trash_dir / self.filename)
        ui.navigate.to("/")


class Article(Item):

    @property
    def journal(self):
        return self.frontmatter.get("journal") or ""

    @journal.setter
    def journal(self, value):
        self.set_key_value("journal", value)

    @property
    def issn(self):
        return self.frontmatter.get("issn", [])

    @issn.setter
    def issn(self, value):
        if value:
            if isinstance(value, str):
                value = value.split(",")
            if not isinstance(value, list):
                raise ValueError
            value = [v.strip() for v in value]
            value = [v for v in value if v]
        if value:
            self.frontmatter["issn"] = value
        else:
            self.frontmatter.pop("issn", None)

    @property
    def volume(self):
        return self.frontmatter.get("volume") or ""

    @volume.setter
    def volume(self, value):
        self.set_key_value("volume", value)

    @property
    def pmid(self):
        return self.frontmatter.get("pmid") or ""

    @pmid.setter
    def pmid(self, value):
        self.set_key_value("pmid", value)

    @property
    def pmc(self):
        return self.frontmatter.get("pmc") or ""

    @pmc.setter
    def pmc(self, value):
        self.set_key_value("pmc", value)

    def from_bibtex(self, fields):
        super().from_bibtex(fields)
        for key in ["journal", "volume", "pmid", "pmc"]:
            try:
                self.set_key_value(key, fields[key])
            except KeyError:
                pass
        self.issn = fields.get("issn")

    def view_additional(self):
        ui.label("Journal:").classes("text-italic")
        with ui.row():
            ui.label(self.journal or "-")
            for issn in self.issn:
                ui.link(
                    f"ISSN {issn}",
                    f"https://portal.issn.org/resource/ISSN/{issn}",
                    new_tab=True,
                )
            ui.label(self.volume or "-").classes("text-weight-bold")
            if self.number:
                ui.label(f"({self.number})")
            ui.label(self.pages or "-")
        ui.label("Links:").classes("text-italic")
        with ui.row():
            if self.doi:
                ui.link(f"DOI {self.doi}", f"https://doi.org/{self.doi}", new_tab=True)
            if self.pmid:
                ui.link(
                    f"PubMed {self.pmid}",
                    f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/",
                    new_tab=True,
                )
            if self.pmc:
                ui.link(
                    self.pmc,
                    f"https://pmc.ncbi.nlm.nih.gov/articles/{self.pmc}/",
                    new_tab=True,
                )
            if self.paperpile:
                ui.link("Paperpile", self.paperpile, new_tab=True)

    def edit_additional(self):
        self.journal_field = ui.input(label="Journal", value=self.journal)
        self.issn_field = ui.input(label="ISSN", value=", ".join(self.issn))
        self.volume_field = ui.input(label="Volume", value=self.volume)
        self.number_field = ui.input(label="Number", value=self.number)
        self.doi_field = ui.input(label="DOI", value=self.doi)
        self.pmid_field = ui.input(label="PubMed", value=self.pmid)
        self.pmc_field = ui.input(label="PMC", value=self.pmc)
        self.paperpile_field = ui.input(label="Paperpile", value=self.paperpile)

    def save_additional(self):
        self.journal = self.journal_field.value
        self.issn = self.issn_field.value
        self.volume = self.volume_field.value
        self.number = self.number_field.value
        self.doi = self.doi_field.value
        self.pmid = self.pmid_field.value
        self.pmc = self.pmc_field.value
        self.paperpile = self.paperpile_field.value


class Book(Item):

    @property
    def isbn(self):
        return self.frontmatter.get("isbn") or ""

    @isbn.setter
    def isbn(self, value):
        self.set_key_value("isbn", value)

    @property
    def series(self):
        return self.frontmatter.get("series") or ""

    @series.setter
    def series(self, value):
        self.set_key_value("series", value)

    def from_bibtex(self, fields):
        super().from_bibtex(fields)
        for key in ["series", "isbn"]:
            try:
                self.set_key_value(key, fields[key])
            except KeyError:
                pass

    def view_additional(self):
        if self.series or self.number:
            ui.label("Series:").classes("text-italic")
            with ui.row():
                if self.series:
                    ui.label(self.series)
                if self.number:
                    ui.label(self.number)
        ui.label("Links:").classes("text-italic")
        with ui.row():
            if self.doi:
                ui.link(f"DOI {self.doi}", f"https://doi.org/{self.doi}", new_tab=True)
            if self.isbn:
                ui.link(
                    f"ISBN {self.isbn}",
                    f"https://isbnsearch.org/isbn/{self.isbn}",
                    new_tab=True,
                )
            if self.paperpile:
                ui.link("Paperpile", self.paperpile, new_tab=True)

    def edit_additional(self):
        self.series_field = ui.input(label="Series", value=self.series)
        self.number_field = ui.input(label="Number", value=self.number)
        self.doi_field = ui.input(label="DOI", value=self.doi)
        self.isbn_field = ui.input(label="ISBN", value=self.isbn)
        self.paperpile_field = ui.input(label="Paperpile", value=self.paperpile)

    def save_additional(self):
        self.series = self.series_field.value
        self.number = self.number_field.value
        self.doi = self.doi_field.value
        self.isbn = self.isbn_field.value
        self.paperpile = self.paperpile_field.value


library = Library()
library.read()


@ui.page("/")
def main():
    global library
    with ui.header().classes(f"text-h5"):
        ui.button(icon="home")
        ui.label(f"Library v{__version__}")
        ui.button(
            "Add BibTex", color="secondary", on_click=lambda: ui.navigate.to("/bibtex")
        )
        ui.button(
            "Add article",
            color="secondary",
            on_click=lambda: ui.navigate.to("/article"),
        )
        ui.button(
            "Add book", color="secondary", on_click=lambda: ui.navigate.to("/book")
        )
        ui.button("Tags", color="info", on_click=lambda: ui.navigate.to("/tags"))
    library.table_setup()


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
    with ui.header().classes(f"text-h5"):
        ui.button(icon="home", on_click=lambda: ui.navigate.to("/"))
        ui.label(f"Add bibtex")
    textarea = ui.textarea(label="BibTex source").classes("w-100")
    with ui.row():
        ui.button("Parse", on_click=lambda: library.parse_bibtex(textarea.value))
        ui.button("Cancel", on_click=lambda: ui.navigate.to("/").props("color=dark"))


@ui.page("/article")
def add_article_page():
    Article().edit()


@ui.page("/book")
def add_book_page():
    Book().edit()


@ui.page("/tags")
def tags_page():
    global library

    def add_tag(tag):
        library.add_tag(tag)
        library.write_tags()
        ui.navigate.to("/tags")

    with ui.header().classes(f"text-h5"):
        ui.button(icon="home", on_click=lambda: ui.navigate.to("/"))
        ui.label("Tags")
    ui.table(
        columns=[
            dict(name="tag", label="Tag", field="tag", align="left"),
            dict(name="number", label="# items", field="number", align="right"),
        ],
        rows=[
            dict(
                tag=t, number=library.count_tagged_items(t), url=f"/tag/{normalize(t)}"
            )
            for t in library.tags
        ],
        row_key="name",
    ).props("bordered").on("row-click", lambda e: ui.navigate.to(e.args[1]["url"]))
    with ui.row(align_items="baseline"):
        tag_field = ui.input(label="New tag")
        ui.button("Add", on_click=lambda: add_tag(tag_field.value))


@ui.page("/tag/{tag}")
def tag_page(tag: str):
    global library
    tag = library.get_tag(normalize(tag))
    if tag is None:
        ui.navigate.to("/tags")
    else:
        with ui.header().classes(f"text-h5"):
            ui.button(icon="home", on_click=lambda: ui.navigate.to("/"))
            ui.label(f"Tag '{tag}'")
        library.table_setup(tags=[tag])
        with ui.row():
            ui.button(
                "Delete", on_click=lambda: ui.navigate.to(f"/tag/{tag}/delete")
            ).props("color=negative")
            ui.button("Cancel", on_click=lambda: ui.navigate.to("/tags")).props(
                "color=dark"
            )


@ui.page("/tag/{tag}/delete")
def tag_delete_page(tag: str):
    global library

    def do_delete():
        library.delete_tag(tag)
        ui.navigate.to("/tags")

    with ui.header().classes(f"text-h5"):
        ui.button(icon="home", on_click=lambda: ui.navigate.to("/"))
        ui.label("Delete tag?")
    ui.label(f"Really delete '{tag}' ?").classes("text-h4")
    with ui.row():
        ui.button("Yes", on_click=do_delete).props("color=negative")
        ui.button("Cancel", on_click=lambda: ui.navigate.to(f"/tag/{tag}")).props(
            "color=dark"
        )


ui.run(title="Library")
