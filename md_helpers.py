""" Helpers to process a markdown file """


def md_create_if_not_exists(file_path):
    """ Create file if not exists """
    try:
        # 'x' mode creates the file (fails if it already exists)
        with open(file_path, 'x', encoding="utf-8"):
            pass
    except FileExistsError:
        pass


def md_get_all(md_path):
    """ Get all MD lines, add a ToDo number to lines that aren't sections """
    with open(md_path, 'r', encoding="utf-8") as file:
        lines = file.readlines()

    if len(lines) == 0:
        return '<empty>'
    if len(lines) == 1 and len(lines[0].strip()) == 0:
        return '<empty>'

    lns = []
    for i, line in enumerate(lines):
        if line.startswith("## ") or len(line.strip()) == 0:
            lns.append(line)
        else:
            lns.append(f'{i} - {line}')

    return ''.join(lns)


def md_get_sections(md_path):
    """ Get sections in a todo markdown file """
    with open(md_path, 'r', encoding="utf-8") as file:
        lines = file.readlines()

    sections = []
    for line in lines:
        if line.startswith("## "):  # Assumes using ## as the header format
            sections.append(line)

    if len(sections) == 0:
        return '<No sections found>'
    return ''.join(sections)


def md_get_section_contents(md_path, section):
    """ Get ToDos in a section of a markdown file """
    if len(section) == 0:
        raise ValueError("Section can't be empty")

    with open(md_path, 'r', encoding="utf-8") as file:
        lines = file.readlines()

    section_found = False
    section_todos = []

    for i, line in enumerate(lines):
        if line.startswith(
                f"## {section}"):  # Assumes using ## as the header format
            section_found = True
            continue
        if section_found:
            if line.startswith('## ') or len(
                    line.strip()) == 0:  # Found a new section
                break
            section_todos.append(f'{i} - {line}')

    if not section_found:
        return f'<No section {section}>'
    if len(section_todos) == 0:
        return f'<{section} is empty>'
    return ''.join(section_todos)


def md_add_to_section(md_path, section, txt):
    """ Append a ToDo to a markdown section """
    if len(section) == 0:
        raise ValueError("Section can't be empty")
    if len(txt) == 0:
        raise ValueError("ToDo can't be empty")

    with open(md_path, 'r', encoding="utf-8") as file:
        lines = file.readlines()

    section_found = False

    for i, line in enumerate(lines):
        if line.lower().startswith(
                f"## {section.lower()}"):  # Assumes using ## as the header format
            section_found = True
            lines.insert(i + 1, f"{txt}\n")
            break

    if not section_found:
        lines.append(f"\n## {section}\n")
        lines.append(f"{txt}\n")

    with open(md_path, 'w', encoding="utf-8") as file:
        file.writelines(lines)


def md_gc_empty_sections(file_path):
    """ Clean emtpy sections from a markdown file """
    with open(file_path, 'r', encoding="utf-8") as file:
        lines = file.readlines()

    gcd_lines = []
    this_section = []
    has_content = False

    for line in lines:
        if line.startswith("## "):
            if has_content:
                gcd_lines.extend(this_section)
            has_content = False
            this_section = []
        if not (line.startswith("## ") or len(line.strip()) == 0):
            has_content = True
        this_section.append(line)

    # If we reach EOF:
    if has_content:
        gcd_lines.extend(this_section)

    # Write back the modified content to the file
    with open(file_path, 'w', encoding="utf-8") as file:
        file.writelines(gcd_lines)


def md_mark_done(file_path, todo_num):
    """ Mark a ToDo done by line number """
    with open(file_path, 'r', encoding="utf-8") as file:
        lines = file.readlines()

    if lines[todo_num].startswith("## "):  # This is a section/header
        return False

    del lines[todo_num]

    with open(file_path, 'w', encoding="utf-8") as file:
        file.writelines(lines)

    md_gc_empty_sections(file_path)
    return True
