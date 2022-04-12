#!/usr/bin/env python3

import argparse
import bs4
import logging
import os
import re
import requests
import sys
import time
import undetected_chromedriver

REPLACEMENT_CHARACTERS = {
    '\u0336': '---',
    '\u2501': '-',
}

def pure_children(element):
    return " ".join([pure_element(child) for child in element.children])

def pure_element(element):
    if isinstance(element, bs4.element.NavigableString):
        return str(element)

    if element.name in ["img", "button"]:
        return ""

    if element.name in ["div", "span", "b", "a"]:
        return pure_children(element)

    return f"{type(element)}: {element}"

def translate_children(element):
    return " ".join([translate_element(child) for child in element.children])

def translate_element(element):
    if isinstance(element, bs4.element.NavigableString):
        return str(element)

    if element.name == "div":
        return translate_children(element)

    if element.name == "p":
        return f"\n{translate_children(element)}\n"

    if element.name == "em" or element.name == "i":
        return f"\\emph{{{translate_children(element)}}}"

    if element.name == "b" or element.name == "strong":
        return f"\\textbf{{{translate_children(element)}}}"

    if element.name == "span":
        if not element.has_attr("style"):
            return translate_children(element)

        if "text-decoration:underline;" in element["style"]:
            return f"\\underline{{{translate_children(element)}}}"

        raise ValueError(f'Unknown style: "{element["style"]}"')

    if element.name == "hr":
        return ""

    if element.name == "br":
        return "\\newline"

    return f"{type(element)}: {element}"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', '-o', action='store', help='The output directory', dest='output', required=True)
    parser.add_argument('urls', metavar='URL', nargs='+', help='The URLs that should be processed')
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')

    if not os.path.isdir(args.output):
        os.makedirs(args.output)

    driver = undetected_chromedriver.Chrome()

    for url in args.urls:
        logging.info("Fetching '%s'...", url)

        driver.get(url)
        time.sleep(1)

        while "Just a moment" in driver.title:
            logging.info("Waiting for page load...")
            time.sleep(5)

        soup = bs4.BeautifulSoup(driver.page_source, "lxml")

        content = soup.body.find('div', attrs={'id': 'storytext'})
        chapters = soup.body.find('select', attrs={'id': 'chap_select'})
        current_chapter = chapters.find('option', attrs={'selected': True})
        profile = soup.body.find('div', attrs={'id': 'profile_top'})
        pure_profile_splits = pure_element(profile).splitlines()

        current_chapter_matches = re.match(r"(\d+)\. (.+)", current_chapter.string)
        onchange_id_match = re.search(r"'/s/(\d+)/'", chapters['onchange'])
        onchange_slug_match = re.search(r"'/(\S+)';", chapters['onchange'])
        story_title_match = re.search(r"^\s+(\S.+\S)\s+$", pure_profile_splits[0])
        story_author_match = re.search(r"^\s+By:\s+(\S.+\S)\s+$", pure_profile_splits[1])
        story_desc_match = re.search(r"^\s+(\S.+\S)\s+$", pure_profile_splits[2])

        story_id = int(onchange_id_match.group(1))
        story_slug = onchange_slug_match.group(1)
        story_title = story_title_match.group(1)
        story_author = story_author_match.group(1)
        story_desc = story_desc_match.group(1)

        chapter_number = int(current_chapter_matches.group(1))
        chapter_title = current_chapter_matches.group(2)

        logging.info("Found chapter %d ('%s') of story %d ('%s')", chapter_number, chapter_title, story_id, story_title)

        translated_content = translate_element(content)

        for key, value in REPLACEMENT_CHARACTERS.items():
            translated_content = translated_content.replace(key, value)

        with open(os.path.join(args.output, f"{story_id}-{story_slug}-{chapter_number:02d}.tex"), "w") as f:
            f.write(f"\\chapter{{{chapter_title}}}\n")
            f.write("\n")
            f.write(translated_content)
            f.write("\n")

        if not os.path.isfile(os.path.join(args.output, f"{story_id}-{story_slug}-00.tex")):
            with open(os.path.join(args.output, f"{story_id}-{story_slug}-00.tex"), "w") as f:
                f.write("\\documentclass{report}\n")
                f.write("\n")
                f.write("\\usepackage[margin=1.5in, footskip=0.25in]{geometry}\n")
                f.write("\n")
                f.write(f"\\title{{{story_title}}}\n")
                f.write(f"\\author{{{story_author}}}\n")
                f.write("\n")
                f.write("\\setlength{\\parindent}{0em}\n")
                f.write("\\setlength{\\parskip}{1em}\n")
                f.write("\n")
                f.write("\\begin{document}\n")
                f.write("\n")
                f.write("\\maketitle\n")
                f.write("\n")

        if not os.path.isfile(os.path.join(args.output, f"{story_id}-{story_slug}-end.tex")):
            with open(os.path.join(args.output, f"{story_id}-{story_slug}-end.tex"), "w") as f:
                f.write("\\end{document}\n")

    driver.close()


if __name__ == '__main__':
    sys.exit(main())
