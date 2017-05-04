#!/usr/bin/env python
#
# Based on src/etc/unicode.py from Rust 1.2.0.
#
# Copyright 2011-2013 The Rust Project Developers.
# Copyright 2015 The Servo Project Developers. See the COPYRIGHT
# file at the top-level directory of this distribution and at
# http://rust-lang.org/COPYRIGHT.
#
# Licensed under the Apache License, Version 2.0 <LICENSE-APACHE or
# http://www.apache.org/licenses/LICENSE-2.0> or the MIT license
# <LICENSE-MIT or http://opensource.org/licenses/MIT>, at your
# option. This file may not be copied, modified, or distributed
# except according to those terms.


import fileinput, re, os, sys, operator


DATA_DIR = 'data'
TESTS_DATA_DIR = 'tests/data'
README_NAME = "ReadMe.txt"
UNICODE_DATA_NAME = "UnicodeData.txt"
TABLES_PATH = os.path.join("src", "char_data", "tables.rs")

PREAMBLE = '''// NOTE:
// The following code was generated by "tools/generate.py". do not edit directly

#![allow(missing_docs, non_upper_case_globals, non_snake_case)]
#![cfg_attr(rustfmt, rustfmt_skip)]
'''

# these are the surrogate codepoints, which are not valid rust characters
surrogate_codepoints = (0xD800, 0xDFFF)

def fetch(name, dst):
    if os.path.exists(dst):
        os.remove(dst)
    os.system("curl -o '%s' 'http://www.unicode.org/Public/UNIDATA/%s'" % (dst, name))
    if not os.path.exists(dst):
        sys.stderr.write("cannot fetch %s" % name)
        exit(1)

def fetch_data(name):
    dst = os.path.join(DATA_DIR, os.path.basename(name))
    fetch(name, dst)

def fetch_test_data(name):
    dst = os.path.join(TESTS_DATA_DIR, os.path.basename(name))
    fetch(name, dst)

def open_data(name):
    return open(os.path.join(DATA_DIR, name))

def is_surrogate(n):
    return surrogate_codepoints[0] <= n <= surrogate_codepoints[1]

def load_unicode_data():
    fetch_data(UNICODE_DATA_NAME)
    udict = {};

    range_start = -1;
    for line in fileinput.input(os.path.join(DATA_DIR, UNICODE_DATA_NAME)):
        data = line.split(';');
        if len(data) != 15:
            continue
        cp = int(data[0], 16);
        if is_surrogate(cp):
            continue
        if range_start >= 0:
            for i in xrange(range_start, cp):
                udict[i] = data;
            range_start = -1;
        if data[1].endswith(", First>"):
            range_start = cp;
            continue;
        udict[cp] = data;

    # Mapping of code point to Bidi_Class property:
    bidi_class = {}

    for code in udict:
        [code_org, name, gencat, combine, bidi,
         decomp, deci, digit, num, mirror,
         old, iso, upcase, lowcase, titlecase ] = udict[code];

        if bidi not in bidi_class:
            bidi_class[bidi] = []
        bidi_class[bidi].append(code)

    # Default Bidi_Class for unassigned codepoints.
    # http://www.unicode.org/Public/UNIDATA/extracted/DerivedBidiClass.txt
    default_ranges = [
        (0x0600, 0x07BF, "AL"), (0x08A0, 0x08FF, "AL"),
        (0xFB50, 0xFDCF, "AL"), (0xFDF0, 0xFDFF, "AL"),
        (0xFE70, 0xFEFF, "AL"), (0x1EE00, 0x1EEFF, "AL"),

        (0x0590, 0x05FF, "R"), (0x07C0, 0x089F, "R"),
        (0xFB1D, 0xFB4F, "R"), (0x10800, 0x10FFF, "R"),
        (0x1E800, 0x1EDFF, "R"), (0x1EF00, 0x1EFFF, "R"),

        (0x20A0, 0x20CF, "ET"),
    ]

    for (start, end, default) in default_ranges:
        for code in range(start, end+1):
            if not code in udict:
                bidi_class[default].append(code)

    return group_categories(bidi_class)

def group_categories(cats):
    cats_out = []
    for cat in cats:
        cats_out.extend([(x, y, cat) for (x, y) in group_cat(cats[cat])])
    cats_out.sort(key=lambda w: w[0])
    return (sorted(cats.keys()), cats_out)

def group_cat(cat):
    cat_out = []
    letters = sorted(set(cat))
    cur_start = letters.pop(0)
    cur_end = cur_start
    for letter in letters:
        assert letter > cur_end, \
            "cur_end: %s, letter: %s" % (hex(cur_end), hex(letter))
        if letter == cur_end + 1:
            cur_end = letter
        else:
            cat_out.append((cur_start, cur_end))
            cur_start = cur_end = letter
    cat_out.append((cur_start, cur_end))
    return cat_out

def format_table_content(f, content, indent):
    line = " "*indent
    first = True
    for chunk in content.split(","):
        if len(line) + len(chunk) < 98:
            if first:
                line += chunk
            else:
                line += ", " + chunk
            first = False
        else:
            f.write(line + ",\n")
            line = " "*indent + chunk
    f.write(line)

def escape_char(c):
    return "'\\u{%x}'" % c

def emit_table(
    file_,
    t_name,
    t_data,
    t_type = "&'static [(char, char)]",
    is_pub=True,
    pfun=lambda x: "(%s,%s)" % (escape_char(x[0]), escape_char(x[1]))
):
    if is_pub:
        file_.write("pub ")
    file_.write("const %s: %s = &[\n" % (t_name, t_type))

    data = ""
    first = True
    for dat in t_data:
        if not first:
            data += ","
        first = False
        data += pfun(dat)
    format_table_content(file_, data, 4)
    file_.write("\n];\n\n")

def emit_bidi_module(file_, bidi_class_table, cats):
    file_.write("""
#[allow(non_camel_case_types)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
/// Represents values of the Unicode character property
/// [Bidi_Class](http://www.unicode.org/reports/tr44/#Bidi_Class), also
/// known as the *bidirectional character type*.
///
/// * http://www.unicode.org/reports/tr9/#Bidirectional_Character_Types
/// * http://www.unicode.org/reports/tr44/#Bidi_Class_Values
pub enum BidiClass {
""")
    for cat in cats:
        file_.write("    " + cat + ",\n")
    file_.write("""}

use self::BidiClass::*;
""")

    emit_table(
        file_,
        "bidi_class_table",
        bidi_class_table,
        "&'static [(char, char, BidiClass)]",
        pfun=lambda x: "(%s,%s,%s)" % (escape_char(x[0]), escape_char(x[1]), x[2]),
    )

def get_unicode_version():
    fetch_data(README_NAME)
    with open_data(README_NAME) as readme:
        pattern = "for Version (\d+)\.(\d+)\.(\d+) of the Unicode"
        return re.search(pattern, readme.read()).groups()

if __name__ == "__main__":
    # Find Unicode Version
    if not os.path.exists(DATA_DIR):
        os.mkdir(DATA_DIR)
    unicode_version = get_unicode_version()

    # Build data tables
    if os.path.exists(TABLES_PATH):
        os.remove(TABLES_PATH)
    with open(TABLES_PATH, "w") as file_:
        file_.write(PREAMBLE)
        file_.write("""
/// The [Unicode version](http://www.unicode.org/versions/) of data
pub const UNICODE_VERSION: (u64, u64, u64) = (%s, %s, %s);
""" % unicode_version)

        (bidi_categories, bidi_class_table) = load_unicode_data()
        emit_bidi_module(file_, bidi_class_table, bidi_categories)

    # Fetch test data files
    fetch_test_data("BidiTest.txt")
    fetch_test_data("BidiCharacterTest.txt")
