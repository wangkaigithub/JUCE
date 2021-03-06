#!/usr/bin/env python

import os
import shutil
import re
import argparse


def get_curly_brace_scope_end(string, start_pos):
    """Given a string and the position of an opening curly brace, find the
       position of the closing brace.
    """
    if string[start_pos] != "{":
        raise ValueError("string must have \"{\" at start pos")
    string_end = len(string)
    bracket_counter = 1
    start_pos += 1
    while start_pos < string_end:
        if string[start_pos] == "{":
            bracket_counter += 1
        elif string[start_pos] == "}":
            bracket_counter -= 1
            if bracket_counter == 0:
                return start_pos
        start_pos += 1
    return -1


def add_doxygen_group(path, group_name):
    """Add a Doxygen group to the file at 'path'.

       Namespaces cause all kinds of problems, and we need to ensure that if
       the classes in a source file are contained within a namespace then we
       also put the @weakgroup inside the namespace.
    """

    filename = os.path.basename(path)
    if re.match(r"^juce_.*\.(h|dox)", filename):
        group_definition_start = ("\r\n/** @weakgroup "
                                  + group_name
                                  + "\r\n *  @{\r\n */\r\n")
        group_definition_end = "\r\n/** @}*/\r\n"

        with open(path, "r") as f:
            content = f.read()

        # Put the group definitions inside all namespaces.
        namespace_regex = re.compile(r"\s+namespace\s+\S+\s+{")
        match = namespace_regex.search(content)
        while (match is not None):
            namespace_end = get_curly_brace_scope_end(content, match.end() - 1)
            if namespace_end == -1:
                raise ValueError("error finding end of namespace "
                                 + match.group()
                                 + " in "
                                 + path)
            content = (content[:match.end()]
                       + group_definition_start
                       + content[match.end():namespace_end]
                       + group_definition_end
                       + content[namespace_end:])
            search_start = (namespace_end
                            + len(group_definition_start)
                            + len(group_definition_end))

            match = namespace_regex.search(content, search_start)

        with open(path, "w") as f:
            f.write(group_definition_start)
            f.write(content)
            f.write(group_definition_end)


###############################################################################

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir",
                        help="the directory to search for source files")
    parser.add_argument("dest_dir",
                        help="the directory in which to place processed files")
    parser.add_argument("--subdirs",
                        help="if specified, only include these comma separated"
                             "subdirectories")
    args = parser.parse_args()

    # Get the list of JUCE modules to include.
    if args.subdirs:
        juce_modules = args.subdirs.split(",")
    else:
        juce_modules = []
        for item in os.listdir(args.source_dir):
            if os.path.isdir(os.path.join(args.source_dir, item)):
                juce_modules.append(item)

    # Copy the JUCE modules to the temporary directory, and process the source
    # files.
    module_definitions = []
    for module_name in juce_modules:

        # Copy the required modules.
        original_module_dir = os.path.join(args.source_dir, module_name)
        module_path = os.path.join(args.dest_dir, module_name)
        shutil.copytree(original_module_dir, module_path)

        # Parse the module header to get module information.
        module_header = os.path.join(module_path, module_name + ".h")
        with open(module_header, "r") as f:
            content = f.read()
        block_info_result = re.match(r".*BEGIN_JUCE_MODULE_DECLARATION"
                                     "(.*)"
                                     "END_JUCE_MODULE_DECLARATION.*",
                                     content,
                                     re.DOTALL)
        detail_lines = []
        for line in block_info_result.group(1).split("\n"):
            stripped_line = line.strip()
            if stripped_line:
                result = re.match(r"^.*?description:\s*(.*)$", stripped_line)
                if result:
                    short_description = result.group(1)
                else:
                    detail_lines.append(stripped_line)

        # The module header causes problems for Doxygen, so delete it.
        os.remove(module_header)

        # Create a Doxygen group definition for the module.
        module_definiton = []
        module_definiton.append("/** @defgroup {n} {n}".format(n=module_name))
        module_definiton.append("    {d}".format(d=short_description))
        module_definiton.append("")
        for line in detail_lines:
            module_definiton.append("    - {l}".format(l=line))
        module_definiton.append("")
        module_definiton.append("    @{")
        module_definiton.append("*/")

        # Create a list of the directories in the module that we can use as
        # subgroups and create the Doxygen group hierarchy string.
        dir_contents = os.listdir(module_path)
        subdirs = [x for x in dir_contents
                   if os.path.isdir(os.path.join(module_path, x))]
        module_groups = {}
        for subdir in subdirs:
            subgroup_name = "{n}-{s}".format(n=module_name, s=subdir)
            module_groups[subgroup_name] = os.path.join(module_path, subdir)
            module_definiton.append("")
            module_definiton.append(
                "/** @defgroup {tag} {n} */".format(tag=subgroup_name, n=subdir)
            )
        module_definiton.append("")
        module_definiton.append("/** @} */")

        module_definitions.append("\r\n".join(module_definiton))

        # Put the top level files into the main group.
        for filename in (set(dir_contents) - set(subdirs)):
            add_doxygen_group(os.path.join(module_path, filename), module_name)

        # Put subdirectory files into their respective groups.
        for group_name in module_groups:
            for dirpath, dirnames, filenames in os.walk(module_groups[group_name]):
                for filename in filenames:
                    try:
                        add_doxygen_group(os.path.join(dirpath, filename), group_name)
                    except:
                        print("Error preprocessing " + filename)
                        continue

    # Create an extra header file containing the module hierarchy.
    with open(os.path.join(args.dest_dir, "juce_modules.dox"), "w") as f:
        f.write("\r\n\r\n".join(module_definitions))
