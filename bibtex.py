"Read and parse BibTex entry. Uses bibtexparser v2."

import string

import bibtexparser

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def parse(bibtex):
    result = []
    for entry in bibtexparser.parse_string(bibtex).entries:
        item = {"type": entry.entry_type}
        item.update(dict([(f.key, f.value) for f in entry.fields]))

        # Post-processing.

        # 'author' -> 'authors' list
        item["authors"] = item.pop("author", "").split(" and ")

        # 'month' to 'published'
        month = item.pop("month", "")
        parts = month.split("#")
        if len(parts) == 2 and parts[1]:
            month = MONTHS[parts[1].strip().casefold()]
            day = int("".join([c for c in parts[0] if c in string.digits]))
            item["published"] = f'{item["year"]}-{month:02d}-{day:02d}'
        elif len(parts) == 1 and parts[0]:
            month = MONTHS[parts[0].strip().casefold()]
            item["published"] = f'{item["year"]}-{month:02d}-01'
        else:
            item["published"] = f'{item["year"]}-01-01'

        # 'pages' double dash to single dash.
        if pages := item.pop("pages", None):
            item["pages"] = pages.replace("--", "-")

        result.append(item)
    return result


if __name__ == "__main__":
    import json

    source = """@BOOK{Tuck2002-ma,
title = "Hobbes: A Very Short Introduction",
author = "Tuck, Richard",
publisher = "Oxford University Press",
address = "London, England",
series = "Very Short Introductions",
month =  dec,
year =  2002,
doi = "10.1093/actrade/9780192802552.001.0001",
isbn =  9780192802552,
}
    @BOOK{Boehm1999-cb,
title = "Hierarchy in the Forest. The Evolution of Egalitarian Behavior",
author = "Boehm, Christopher",
publisher = "Harvard University Press",
address = "London, England",
year =  1999,
isbn =  9780674006911,
}
@BOOK{Darwin2013-cv,
title = "The descent of man",
author = "Darwin, Charles",
publisher = "Wordsworth Editions",
address = "Ware, England",
series = "Wordsworth Classics of World Literature",
month =  "8~" # jul,
year =  2013,
isbn =  9781840226980,
}
@ARTICLE{Enright2017-ak,
title = "'To the victor go the spoils': Infants expect resources to align with dominance structures",
author = "Enright, Elizabeth A and Gweon, Hyowon and Sommerville, Jessica A",
journal = "Cognition",
publisher = "Elsevier",
volume =  164,
pages = "8--21",
abstract = "Previous research has found that within the first year of life infants possess rich knowledge about social structures (i.e., that some individuals are dominant over other individuals) as well as expectations about resource distributions (i.e., that resources are typically distributed equally to recipients). We investigated whether infants' expectations about resource distribution can be modulated by information about the dominance structure between the recipients. We first replicated the finding that infants attribute a stable dominance hierarchy to a pair of individuals when their goals conflicted and one individual yielded to the other (Expt. 1), and that this sensitivity is not driven by lower-level perceptual factors (Expt. 2). In Experiments 3-5, we tested our main hypothesis that infants' attention to equal and unequal distributions varies as a function of prior social dominance information. We first replicated and extended prior work by establishing that infants looked significantly longer to unequal than equal resource distributions when no prior information about dominance was provided about recipients (Expt. 3). Critically, following social dominance information, infants looked significantly longer to an equal distribution of resources than a distribution that favored the dominant individual (Expt. 4), and looked significantly longer when the submissive individual received more resources compared to when the dominant individual received more resources (Expts. 4 and 5). Together, these findings suggest that infants expect resources to align with social dominance structures.",
month =  "1~" # jul,
year =  2017,
keywords = "Inequality; Infant social cognition; Resource distributions; Social dominance",
doi = "10.1016/j.cognition.2017.03.008",
pmc = "PMC5839744",
pmid =  28346870,
issn = "0010-0277,1873-7838",
}
@ARTICLE{Kay2026-bb,
title = "Dated gene duplications elucidate the evolutionary assembly of eukaryotes",
author = "Kay, Christopher J and Spang, Anja and Szöllősi, Gergely J and Pisani, Davide and Williams, Tom A and Donoghue, Philip C J",
journal = "Nature",
publisher = "Springer Science and Business Media LLC",
volume =  650,
number =  8100,
pages = "129--140",
abstract = "The origin of eukaryotes was a formative but poorly understood event in the history of life. Current hypotheses of eukaryogenesis differ principally in the timing of mitochondrial endosymbiosis relative to the acquisition of other eukaryote novelties1. Discriminating among these hypotheses has been challenging, because there are no living lineages representative of intermediate steps within eukaryogenesis. However, many eukaryotic cell functions are contingent on genes that emerged from duplication events during eukaryogenesis2,3. Consequently, the timescale of these duplications can provide insights into the sequence of steps in the evolutionary assembly of the eukaryotic cell. Here we show, using a relaxed molecular clock4, that the process of eukaryogenesis spanned the Mesoarchaean to late Palaeoproterozoic eras. Within these constraints, we dated the timing of these gene duplications, revealing that the eukaryotic host cell already had complex cellular features before mitochondrial endosymbiosis, including an elaborated cytoskeleton, membrane trafficking, endomembrane, phagocytotic machinery and a nucleus, all between 3.0 and 2.25 billion years ago, after which mitochondrial endosymbiosis occurred. Our results enable us to reject mitochondrion-early scenarios of eukaryogenesis5, instead supporting a complexified-archaean, late-mitochondrion sequence for the assembly of eukaryote characteristics. Our inference of a complex archaeal host cell is compatible with hypotheses on the adaptive benefits of syntrophy6,7 in oceans that would have remained largely anoxic for more than a billion years8,9.",
month =  feb,
year =  2026,
doi = "10.1038/s41586-025-09808-z",
pmid =  41339551,
issn = "0028-0836,1476-4687",
}

    """
    for data in parse(source):
        print(json.dumps(data, indent=2, ensure_ascii=False))
