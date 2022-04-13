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
    '&': '\\&',
    '$': '\\$',
    '_': '\\_',
    '#': '\\#',
    '~': '\\textasciitilde',
}

CLEANUP_REPLACEMENTS = {
    r'[^\S\r\n]+(\\(?:emph){)[^\S\r\n]+': r' \1',
    r'[^\S\r\n]+}[^\S\r\n]+': r'} ',
    r'[^\S\r\n]+([,.?!:])': r'\1',
    r'(["])[^\S\r\n]+(\\(?:emph){)': r'\1\2',
}

LIKE_WHITESPACE = (
    ' ',
    '\n',
)

def join_strings(strings):
    result = ""

    for string in strings:
        if len(result) > 0 and len(string) > 0 and result[-1] not in LIKE_WHITESPACE and string[0] not in LIKE_WHITESPACE:
            result += " "

        result += string

    return result

def pure_children(element):
    return join_strings([pure_element(child) for child in element.children])

def pure_element(element):
    if isinstance(element, bs4.element.NavigableString):
        return str(element)

    if element.name in ["img", "button"]:
        return ""

    if element.name in ["div", "span", "b", "a"]:
        return pure_children(element)

    return f"{type(element)}: {element}"

def translate_children(element):
    return join_strings([translate_element(child) for child in element.children])

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
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug output', dest='debug')
    parser.add_argument('--cleanup', '-c', action='store_true', help='Enable cleanup of the output text', dest='cleanup')
    parser.add_argument('urls', metavar='URL', nargs='+', help='The URLs that should be processed')
    args = parser.parse_args()

    logger = logging.getLogger('ff2latex')
    logger_handler = logging.StreamHandler()
    logger_handler.setFormatter(logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(logger_handler)
    logger.setLevel(logging.DEBUG if args.debug else logging.INFO)

    if not os.path.isdir(args.output):
        os.makedirs(args.output)

    driver = undetected_chromedriver.Chrome()

    for url in args.urls:
        logger.info("Fetching '%s'...", url)

        driver.get(url)
        time.sleep(1)

        while "FanFiction" not in driver.title:
            logger.info("Waiting for page load...")
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
        story_title_match = re.search(r"^\s*(\S.*\S)\s*$", pure_profile_splits[0])
        story_author_match = re.search(r"^\s*By:\s+(\S.*\S)\s*$", pure_profile_splits[1])
        story_desc_match = re.search(r"^\s*(\S.*\S)\s*$", pure_profile_splits[2])

        try:
            story_id = int(onchange_id_match.group(1))
            story_slug = onchange_slug_match.group(1)
        except AttributeError:
            logger.exception("Failed to match story metadata")
            logger.debug("chapters['onchange']: '%s'", chapters['onchange'])
            return

        try:
            story_title = story_title_match.group(1)
            story_author = story_author_match.group(1)
            story_desc = story_desc_match.group(1)
        except AttributeError:
            logger.exception("Failed to match story information")
            logger.debug("pure_profile_splits: '%s'", pure_profile_splits)
            return

        try:
            chapter_number = int(current_chapter_matches.group(1))
            chapter_title = current_chapter_matches.group(2)
        except AttributeError:
            logger.exception("Failed to match current chapter")
            logger.debug("current_chapter.string: '%s'", current_chapter.string)
            return


        logger.info("Found chapter %d ('%s') of story %d ('%s')", chapter_number, chapter_title, story_id, story_title)

        translated_content = translate_element(content)

        for key, value in REPLACEMENT_CHARACTERS.items():
            chapter_title = chapter_title.replace(key, value)
            translated_content = translated_content.replace(key, value)

        if args.cleanup:
            for key, value in CLEANUP_REPLACEMENTS.items():
                translated_content = re.sub(key, value, translated_content)

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
