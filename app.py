import streamlit as st
import imaplib
import email
import re
import csv
import os
import unicodedata
import hashlib

# Set page config first!
st.set_page_config(
    page_title="PCG Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

def check_password():
    def password_entered():
        if st.session_state["password"] == "7bpsBG6vJz":
            st.session_state["authenticated"] = True
            del st.session_state["password"]  # remove password from memory
        else:
            st.session_state["authenticated"] = False

    if "authenticated" not in st.session_state:
        st.text_input("Password:", type="password", on_change=password_entered, key="password")
        st.stop()
    elif not st.session_state["authenticated"]:
        st.text_input("Password:", type="password", on_change=password_entered, key="password")
        st.error("😕 Incorrect password")
        st.stop()

check_password()

# ========== UTILITY FUNCTIONS ==========

def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def normalize_simple_firstlast(name):
    name = remove_accents(name)
    words = [w for w in name.replace(",", " ").split() if w]
    if not words:
        return ""
    if len(words) == 1:
        return words[0].lower()
    return (words[0] + " " + words[-1]).lower()

def normalize_title(title):
    return re.sub(r'[^\w\s]', '', title).strip().lower()

# Add this with the other filename declarations (around line 37)
declined_filename = "declined_papers.csv"
optioned_filename = "optioned_papers.csv"
solicited_filename = "solicited_papers.csv"  # Add this linestrea

def read_declined_set():
    declined = set()
    if os.path.exists(declined_filename):
        with open(declined_filename, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row.get("paper_id") or ""
                if pid:
                    declined.add(row.get("paper_id"))
    return declined

def load_optioned_papers():
    papers = []
    if os.path.exists(optioned_filename):
        with open(optioned_filename, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = row.get('title', "")
                authors = [a.strip() for a in row.get('authors', "").split(';') if a.strip()]
                # new fields:
                journal = row.get('journal', "")
                affils = row.get('affiliations', "")
                affiliations = [a.strip() for a in affils.split(';') if a.strip()]
                papers.append({
                    'title': title,
                    'authors': authors,
                    'affiliations': affiliations,
                    'journal': journal,
                })
    return papers

def read_solicited_set():
    solicited = set()
    if os.path.exists(solicited_filename):
        with open(solicited_filename, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row.get("paper_id", "")
                if pid:
                    solicited.add(pid)
    return solicited

def append_declined(title, author_list):
    file_exists = os.path.exists(declined_filename)
    first_author = author_list[0].strip() if author_list else ""
    paper_id = generate_paper_id(title, first_author)
    with open(declined_filename, "a", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "paper_id", "title", "first_author", "authors", "norm_title", "norm_first_author"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "paper_id": paper_id,
            "title": title.strip(),
            "first_author": first_author,
            "authors": "; ".join([a.strip() for a in author_list]),
            "norm_title": normalize_title(title),
            "norm_first_author": normalize_simple_firstlast(first_author)
        })

def append_optioned(title, author_list, affiliations, journal):
    file_exists = os.path.exists(optioned_filename)
    first_author = author_list[0].strip() if author_list else ""
    paper_id = generate_paper_id(title, first_author)
    with open(optioned_filename, "a", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "paper_id", "title", "first_author", "authors",
            "journal", "affiliations",
            "norm_title", "norm_first_author"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "paper_id": paper_id,
            "title": title.strip(),
            "first_author": first_author,
            "authors": "; ".join(a.strip() for a in author_list),
            "journal": journal or "",
            "affiliations": "; ".join(a.strip() for a in affiliations),
            "norm_title": normalize_title(title),
            "norm_first_author": normalize_simple_firstlast(first_author)
        })

def append_solicited(title, author_list, affiliations, journal):
    file_exists = os.path.exists(solicited_filename)
    first_author = author_list[0].strip() if author_list else ""
    paper_id = generate_paper_id(title, first_author)
    with open(solicited_filename, "a", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "paper_id", "title", "first_author", "authors",
            "journal", "affiliations",
            "norm_title", "norm_first_author"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "paper_id": paper_id,
            "title": title.strip(),
            "first_author": first_author,
            "authors": "; ".join(a.strip() for a in author_list),
            "journal": journal or "",
            "affiliations": "; ".join(a.strip() for a in affiliations),
            "norm_title": normalize_title(title),
            "norm_first_author": normalize_simple_firstlast(first_author)
        })


def read_optioned_set():
    """
    Returns a set of paper_id for every row in optioned_papers.csv,
    computing legacy IDs if no paper_id column exists.
    """
    optioned = set()
    if not os.path.exists(optioned_filename):
        return optioned

    with open(optioned_filename, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row.get("paper_id", "")
            if pid:
                optioned.add(pid)
    return optioned

    header = rows[0]
    has_pid = "paper_id" in header
    # locate the norm_* columns
    idx_title = header.index("title")
    idx_author = header.index("first_author")
    idx_norm_title = header.index("norm_title")
    idx_norm_first = header.index("norm_first_author")
    pid_idx = header.index("paper_id") if has_pid else None

    for row in rows[1:]:
        if has_pid:
            pid = row[pid_idx]
        else:
            norm_title = row[idx_norm_title]
            norm_first = row[idx_norm_first]
            pid = hashlib.md5((norm_title + norm_first).encode("utf-8")).hexdigest()
        optioned.add(pid)

    return optioned


def remove_optioned(title, author_list):
    norm_title = normalize_title(title)
    norm_first_author = normalize_simple_firstlast(author_list[0]) if author_list else ""
    if not os.path.exists(optioned_filename):
        return
    rows = []
    with open(optioned_filename, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("norm_title") == norm_title and row.get("norm_first_author") == norm_first_author:
                continue
            rows.append(row)
    with open(optioned_filename, "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "paper_id", "title", "first_author", "authors",
            "journal", "affiliations",
            "norm_title", "norm_first_author"
        ])
        writer.writeheader()
        writer.writerows(rows)

def generate_paper_id(title, first_author):
    norm_title = normalize_title(title)
    norm_author = normalize_simple_firstlast(first_author)
    combined = norm_title + norm_author
    return hashlib.md5(combined.encode('utf-8')).hexdigest()

solicitable_author_simple = set()
with open('solicitable_authors.csv', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    header = reader.fieldnames[0]
    for row in reader:
        fullname = row.get(header, '').strip()
        norm = normalize_simple_firstlast(fullname)
        if norm:
            solicitable_author_simple.add(norm)

def collapse_multiline_titles(text):
    lines = text.split('\n')
    collapsed = []
    i = 0
    while i < len(lines):
        # Detect line like "1." or "23." — numbered title markers
        if re.match(r"^\s*\d+\.\s*$", lines[i]):
            i += 1
            title_lines = []
            # Gather next lines that are likely part of the title
            while i < len(lines) and lines[i].strip() and not re.match(r"^(Posted:|Downloads|Number of pages:|Keywords:)", lines[i]):
                title_lines.append(lines[i].strip())
                i += 1
            collapsed_title = ' '.join(title_lines).strip()
            collapsed.append(f"# Title: {collapsed_title}")
        else:
            collapsed.append(lines[i])
            i += 1
    return '\n'.join(collapsed)

def tag_author_lines(text):
    lines = text.splitlines()
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)

        if line.startswith("# Title:"):
            j = i + 1
            # Skip blank lines
            while j < len(lines) and not lines[j].strip():
                new_lines.append(lines[j])
                j += 1
            # Skip # Publication line if present
            if j < len(lines) and lines[j].startswith("# Publication:"):
                new_lines.append(lines[j])
                j += 1
                while j < len(lines) and not lines[j].strip():
                    new_lines.append(lines[j])
                    j += 1
            # Tag first author line
            if j < len(lines) and not lines[j].startswith("#"):
                new_lines.append("# Authors: " + lines[j])
                j += 1
                # Continue with rest of the body
                i = j - 1
        i += 1

    return "\n".join(new_lines)

def flatten_author_blocks(text):
    lines = text.splitlines()
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith("# Authors:"):
            # Start collecting block
            block = [line.replace("# Authors:", "").strip()]
            i += 1
            blank_seen = False

            while i < len(lines):
                current = lines[i].strip()

                # Stop if we hit a new section or a second blank line
                if current.startswith("#"):
                    break
                if current == "":
                    if blank_seen:
                        break
                    blank_seen = True
                    i += 1
                    continue

                block.append(current)
                i += 1

            flattened = " ".join(block).strip()
            new_lines.append(f"# Author: {flattened}")
        else:
            new_lines.append(line)
            i += 1

    return "\n".join(new_lines)

def split_authors_affiliations(body):
    lines = body.splitlines()
    new_lines = []

    # Common affiliation indicators
    affiliation_keywords = {'University', 'School', 'College', 'Institute', 'Center', 'Faculty', 'Department'}

    for line in lines:
        if line.startswith("# Author:"):
            content = line[len("# Author:"):].strip()

            # Handle sole author cases with affiliation leakage
            if ' and ' not in content and ',' not in content:
                tokens = content.split()
                if len(tokens) >= 4:
                    for i in range(2, min(5, len(tokens))):
                        name = " ".join(tokens[:i])
                        remainder = " ".join(tokens[i:])
                        if any(word in affiliation_keywords for word in remainder.split()):
                            new_lines.append("# Author: " + name)
                            new_lines.append("# Affiliation: " + remainder)
                            break
                    else:
                        new_lines.append(line)  # couldn't confidently split
                else:
                    new_lines.append(line)
                continue

            # Handle multiple authors
            and_index = content.find(" and ")
            if and_index == -1:
                new_lines.append(line)
                continue

            before_and = content[:and_index]
            after_and = content[and_index + len(" and "):].strip()

            tokens = re.findall(r'\b[A-Z][a-zA-Z\.\']*\b', after_and)

            if len(tokens) >= 2:
                cutoff = f"{tokens[0]} {tokens[1]}"
                split_match = re.search(re.escape(cutoff), after_and)
                if split_match:
                    split_point = split_match.end()
                    final_author = after_and[:split_point].strip()
                    affiliations = after_and[split_point:].strip()

                    new_lines.append("# Author: " + before_and.strip() + " and " + final_author)
                    if affiliations:
                        new_lines.append("# Affiliation: " + affiliations)
                    continue

            new_lines.append(line)  # fallback
        else:
            new_lines.append(line)

    return "\n".join(new_lines)

def fetch_all_ssrn_emails():
    imap_host = "imap.gmail.com"
    username = "PCGssrn@gmail.com"
    app_password = "lbcf ioir uuoy wqui"  # GMAIL PASSWORD

    print("Connecting to Gmail...")
    mail = imaplib.IMAP4_SSL(imap_host)
    mail.login(username, app_password)
    print("Login successful.")

    mail.select("INBOX")
    status, message_numbers = mail.search(None, "ALL")

    if status != "OK":
        print("No emails found.")
        mail.logout()
        return []

    emails = []
    for num in message_numbers[0].split():
        status, msg_data = mail.fetch(num, '(RFC822)')
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                body = ""

                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain" and part.get("Content-Disposition") is None:
                            charset = part.get_content_charset() or "utf-8"
                            body += part.get_payload(decode=True).decode(charset, errors="ignore")
                else:
                    charset = msg.get_content_charset() or "utf-8"
                    body = msg.get_payload(decode=True).decode(charset, errors="ignore")

                body = re.sub(r"<[^>]+>", "", body)
                body = re.sub(
                    r"^Number of pages: \d+\s+Posted: \d{1,2} [A-Z][a-z]{2} 202\d(?:\s+Last Revised: \d{1,2} [A-Z][a-z]{2} 202\d)?\s*$",
                    "",
                    body,
                    flags=re.MULTILINE
                )
                body = re.sub(r"^Posted: \d{1,2} [A-Z][a-z]{2} 202\d\s*$", "", body, flags=re.MULTILINE)
                body = re.sub(r"^Downloads\d+\s*$", "", body, flags=re.MULTILINE)
                body = re.sub(
                    r"^(Fiduciary|Shareholder|Hedge Funds|Mutual Funds|ESG|Institutional Investors|Corporate|Stakeholder|Merger|Directors|Compensation|Securities|SPAC|Proxy Advisors)\s*$",
                    "",
                    body,
                    flags=re.MULTILINE
                )
                body = re.sub(
                    r"^Keywords:.*\n(?:^[^\S\r\n]*\S.*\n)?",
                    "",
                    body,
                    flags=re.MULTILINE
                )
                body = collapse_multiline_titles(body)
                body = body.replace("*affiliation not provided to SSRN*", "No affiliation")
                body = re.sub(r"\*affiliation\s+(?:not\s+provided\s+to\s+SSRN)\*", "No affiliation", body, flags=re.IGNORECASE)
                body = re.sub(r"^Body preview:\s*$", "", body, flags=re.MULTILINE)


                body = re.sub(
                    r"\*(.*?)\n(.*?)\*\s*",  # Two-line version
                    lambda m: f"# Publication: {m.group(1).strip()} {m.group(2).strip()}\n\n",
                    body
                )
                body = re.sub(
                    r"\*(.*?)\*\s*",  # Single-line version
                    lambda m: f"# Publication: {m.group(1).strip()}\n\n",
                    body
                )

                body = re.sub(
                    r"(#\.\n)([^\n]*\n)(# Publication:)",
                    r"\1\3",
                    body
                )

                body = re.sub(r"\[image: Multiple version icon\]There are \d+ versions of this paper", "", body)

                body = re.sub(r'(\n\s*){2,}', '\n\n', body)

                body = tag_author_lines(body)
                body = flatten_author_blocks(body)
                body = split_authors_affiliations(body)

                emails.append({
                    "body": body.strip()
                })


    mail.logout()
    print(f"Fetched {len(emails)} emails.")
    return emails

def deduplicate_papers(papers):
    seen = set()
    unique = []
    for paper in papers:
        key = (
            normalize_title(paper['title']),
            normalize_simple_firstlast(paper['authors'][0]) if paper.get('authors') else ""
        )
        if key not in seen:
            seen.add(key)
            unique.append(paper)
    return unique

def escape_angle_brackets(text):
    if not text:
        return ""
    return text.replace('<', '&lt;').replace('>', '&gt;')

def remove_urls(text):
    if not text:
        return ""
    return re.sub(r'https?://\S+|www\.\S+', '', text).strip()

def strip_all_hyperlinks(text):
    return re.sub(r'\s*<[^>]*>', '', text).strip()

def remove_downloads_trailer(text):
    text = re.sub(r'(,)?\s*Downloads,?\s*\d+\s*$', '', text).strip()
    text = re.sub(r',\s*\d+\s*$', '', text).strip()
    text = re.sub(r'(?:,|\band\b)?\s*\d+\s*$', '', text).strip()
    return text

def split_authors(authors_line):
    authors_line = authors_line.strip()
    authors_line = re.sub(r'\s*\(\d+\)\s*$', '', authors_line)  # remove trailing numeric refs like (1)

    # Handle final author introduced by " and "
    if ' and ' in authors_line:
        pre_and, final_author = authors_line.rsplit(' and ', 1)
        authors = [a.strip() for a in pre_and.split(',') if a.strip()]
        authors.append(final_author.strip())
        return authors
    else:
        # No "and" — assume a single author or malformed input
    
        return [a.strip() for a in authors_line.split(',') if a.strip()]


def split_affiliations(affil_line):
    affil_line = affil_line.strip()
    affil_line = re.sub(r'\s*\(\d+\)\s*$', '', affil_line)  # Remove trailing numeric refs like (1)

    # Handle " and " before final affiliation
    if ' and ' in affil_line:
        pre_and, final_affil = affil_line.rsplit(' and ', 1)
        parts = [a.strip() for a in pre_and.split(',') if a.strip()]
        parts.append(final_affil.strip())
        return parts
    else:
        return [a.strip() for a in affil_line.split(',') if a.strip()]

def extract_papers_from_body(text):
    lines = text.strip().splitlines()
    papers = []
    title = None
    journal = None
    authors_line = None
    affils_line = None

    for line in lines:
        line = line.strip()
        if line.startswith("# Title:"):
            # Start a new paper block
            if title and authors_line:
                authors = split_authors(authors_line)
                affiliations = split_affiliations(affils_line) if affils_line else [""] * len(authors)
                if len(affiliations) < len(authors):
                    affiliations += [""] * (len(authors) - len(affiliations))
                elif len(affiliations) > len(authors):
                    affiliations = affiliations[:len(authors)]

                papers.append({
                    'title': title,
                    'authors': authors,
                    'authors_lower': [a.lower() for a in authors],
                    'affiliations': affiliations,
                    'journal': journal,
                })

            # Reset all fields
            title = line[len("# Title:"):].strip()
            journal = None
            authors_line = None
            affils_line = None

        elif line.startswith("# Publication:"):
            journal = line[len("# Publication:"):].strip()

        elif line.startswith("# Author:") or line.startswith("# Authors:"):
            authors_line = line.split(":", 1)[1].strip()

        elif line.startswith("# Affiliation:") or line.startswith("# Affiliations:"):
            affils_line = line.split(":", 1)[1].strip()

    # Don't forget the last paper in the loop
    if title and authors_line:
        authors = split_authors(authors_line)
        affiliations = split_affiliations(affils_line) if affils_line else [""] * len(authors)
        if len(affiliations) < len(authors):
            affiliations += [""] * (len(authors) - len(affiliations))
        elif len(affiliations) > len(authors):
            affiliations = affiliations[:len(authors)]

        papers.append({
            'title': title,
            'authors': authors,
            'authors_lower': [a.lower() for a in authors],
            'affiliations': affiliations,
            'journal': journal,
        })

    return papers

def get_all_papers_filtered():
    try:
        emails = fetch_all_ssrn_emails()
        declined_set = read_declined_set()
        optioned_set = read_optioned_set()
        solicited_set = read_solicited_set()
        new_papers = []
        
        for email in emails:
            try:
                extracted_papers = extract_papers_from_body(email["body"])
                for paper in extracted_papers:
                    try:
                        authors = paper.get("authors", [])
                        # Safely get first author
                        first_author = ""
                        if isinstance(authors, list) and len(authors) > 0 and authors[0]:
                            first_author = str(authors[0])
                        
                        title = paper.get("title", "")
                        if not title:  # Skip papers without titles
                            continue
                            
                        pid = generate_paper_id(title, first_author)
                        # Skip if already declined, optioned, or solicited
                        if pid in declined_set or pid in optioned_set or pid in solicited_set:
                            continue
                        new_papers.append(paper)
                    except Exception as paper_error:
                        st.warning(f"Error processing individual paper: {paper_error}")
                        continue
            except Exception as email_error:
                st.warning(f"Error extracting papers from email: {email_error}")
                continue

        return deduplicate_papers(new_papers)

    except Exception as outer_error:
        st.error(f"Unexpected error while fetching and filtering papers: {outer_error}")
        return []

        

def load_solicited_papers():
    papers = []
    if os.path.exists(solicited_filename):
        with open(solicited_filename, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = row.get('title', "")
                authors = [a.strip() for a in row.get('authors', "").split(';') if a.strip()]
                journal = row.get('journal', "")
                affils = row.get('affiliations', "")
                affiliations = [a.strip() for a in affils.split(';') if a.strip()]
                papers.append({
                    'title': title,
                    'authors': authors,
                    'affiliations': affiliations,
                    'journal': journal,
                })
    return papers

def append_solicited_accepted(title, author_list, affiliations, journal):
    file_exists = os.path.exists("solicited_accepted.csv")
    first_author = author_list[0].strip() if author_list else ""
    paper_id = generate_paper_id(title, first_author)
    with open("solicited_accepted.csv", "a", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "paper_id", "title", "first_author", "authors",
            "journal", "affiliations",
            "norm_title", "norm_first_author"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "paper_id": paper_id,
            "title": title.strip(),
            "first_author": first_author,
            "authors": "; ".join(a.strip() for a in author_list),
            "journal": journal or "",
            "affiliations": "; ".join(a.strip() for a in affiliations),
            "norm_title": normalize_title(title),
            "norm_first_author": normalize_simple_firstlast(first_author)
        })

def append_solicited_declined(title, author_list, affiliations, journal):
    file_exists = os.path.exists("solicited_declined.csv")
    first_author = author_list[0].strip() if author_list else ""
    paper_id = generate_paper_id(title, first_author)
    with open("solicited_declined.csv", "a", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "paper_id", "title", "first_author", "authors",
            "journal", "affiliations",
            "norm_title", "norm_first_author"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "paper_id": paper_id,
            "title": title.strip(),
            "first_author": first_author,
            "authors": "; ".join(a.strip() for a in author_list),
            "journal": journal or "",
            "affiliations": "; ".join(a.strip() for a in affiliations),
            "norm_title": normalize_title(title),
            "norm_first_author": normalize_simple_firstlast(first_author)
        })

def remove_solicited(title, author_list):
    norm_title = normalize_title(title)
    norm_first_author = normalize_simple_firstlast(author_list[0]) if author_list else ""
    if not os.path.exists(solicited_filename):
        return
    rows = []
    with open(solicited_filename, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("norm_title") == norm_title and row.get("norm_first_author") == norm_first_author:
                continue  # skip this one
            rows.append(row)
    with open(solicited_filename, "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "paper_id", "title", "first_author", "authors",
            "journal", "affiliations",
            "norm_title", "norm_first_author"
        ])
        writer.writeheader()
        writer.writerows(rows)

# ========== SESSION STATE INITIALIZATION ==========

if "papers_to_show" not in st.session_state:
    st.session_state["papers_to_show"] = get_all_papers_filtered()
if "optioned_papers" not in st.session_state:
    st.session_state["optioned_papers"] = load_optioned_papers()
if "solicited_papers" not in st.session_state:
    st.session_state["solicited_papers"] = load_solicited_papers()
if "show_email_draft" not in st.session_state:
    st.session_state["show_email_draft"] = False
if "draft_paper_data" not in st.session_state:
    st.session_state["draft_paper_data"] = None
solicited_set = read_solicited_set()
if "optioned_papers" not in st.session_state:
    optioned_papers = load_optioned_papers()
    filtered_optioned_papers = []
    for paper in optioned_papers:
        pid = generate_paper_id(paper["title"], paper["authors"][0] if paper.get("authors") else "")
        if pid not in solicited_set:
            filtered_optioned_papers.append(paper)
    st.session_state["optioned_papers"] = filtered_optioned_papers
if "manual_email_edit" not in st.session_state:
    st.session_state["manual_email_edit"] = False
if "manual_email_text" not in st.session_state:
    st.session_state["manual_email_text"] = ""

# ========== UI ==========

st.sidebar.title("PCG Dashboard")
st.sidebar.image("harvard.png", width=120)

page = st.sidebar.radio(
    "Navigate",
    ["Dashboard", "Declined Papers"]
)

if page == "Dashboard":

    if st.session_state.get("show_email_draft") and st.session_state.get("draft_paper_data"):
        paper = st.session_state["draft_paper_data"]
        authors = paper.get("authors", [])

        status_options = ["fast track", "prominent", "solid", "rising", "obscure", "exclude"]
        authors_line = ""
        subject = f"Academic Option – {paper.get('title', '')}"
       
        if authors:
            last_names = [a.split()[-1] for a in authors]
            subject = f"Academic Option – {', '.join(last_names)} ({paper.get('title', '')})"
            
            st.markdown("### Author Statuses")

            status_options = ["fast track", "prominent", "solid", "rising", "obscure", "exclude"]
            discipline_options = ["law", "finance", "accounting", "economics", "business"]
            
        for i, name in enumerate(last_names):
            status_key = f"status_selected_{name}"
            field_key = f"field_selected_{name}"
            affil_key = f"edited_affiliation_{name}"

            st.markdown(f"**{name}**")

            if status_key in st.session_state and field_key in st.session_state:
                original_affil = paper.get("affiliations", [])[i] if i < len(paper.get("affiliations", [])) else ""
                current_affil = st.session_state.get(affil_key, original_affil)

                st.text_input(
                    f"Affiliation for {name}",
                    value=current_affil,
                    key=affil_key
                )

                st.markdown(
                    f"{name} is marked as **{st.session_state[status_key]} {st.session_state[field_key]} professor** at {st.session_state[affil_key]}."
                )
    
            elif status_key in st.session_state:
                st.markdown(f"**{name}** is marked as **{st.session_state[status_key]}**. Now select discipline:")
                cols = st.columns(len(discipline_options))
                for j, field in enumerate(discipline_options):
                    if cols[j].button(field.capitalize(), key=f"{name}_{field}"):
                        st.session_state[field_key] = field
                        st.rerun()

            else:
                cols = st.columns(len(status_options))
                for j, option in enumerate(status_options):
                    if cols[j].button(option.capitalize(), key=f"{name}_{option}"):
                        st.session_state[status_key] = option
                        st.rerun()

            if all(f"status_selected_{name}" in st.session_state for name in last_names):
                descriptor = (
                    "professor at a [top (5), 1st tier (6-20), 2nd tier (21-50), 3rd tier (50 and under), unranked, European (including UK), non-US, top European (Oxford or Cambridge), top non-US] university (<affiliation>)"
                )
                
                affiliations = paper.get("affiliations", []) 
                
                elite_us_law = {"Harvard", "Stanford", "Yale", "Chicago", "Virginia", "Penn"}
                elite_us_business = {"Penn", "Northwestern", "Stanford", "Chicago", "MIT"}
                first_us_law = {"Duke", "NYU", "Michigan", "Columbia", "Northwestern", "UCLA", "Berkeley", "Georgetown", "UT Austin", "Vanderbilt", "Wash U", "Washington University", "Cornell", "UNC", "Minnesota"}
                first_us_business = {"Tuck", "Dartmouth", "Harvard", "NYU", "Columbia", "Yale", "Berkeley", "Virginia", "Duke", "Michigan", "Cornell", "UT Austin", "Emory", "Carnegie Mellon", "UCLA", "Vanderbilt", "GIT", "Georgia Institute of Technology"}
                
                author_descriptions = []
                affiliations = paper.get("affiliations", []) 

                for name in last_names:
                    status = st.session_state.get(f"status_selected_{name}")
                    field = st.session_state.get(f"field_selected_{name}")
                    affil = st.session_state.get(f"edited_affiliation_{name}", "")
                    if not affil:
                        affil = affiliations[last_names.index(name)] if last_names.index(name) < len(affiliations) else ""

                    if status and field and status != "exclude":
                        affil_clean = affil.strip()

                        affil_lower = affil_clean.lower()
                        if field == "law":
                            if any(school.lower() in affil_lower for school in elite_us_law):
                                tier_descriptor = "top"
                            elif any(school.lower() in affil_lower for school in first_us_law):
                                tier_descriptor = "1st tier"
                            else:
                                tier_descriptor = "[2nd tier (21-50), 3rd tier (50 and under), unranked, European (including UK), non-US, top European (Oxford or Cambridge), top non-US]"
                        else:
                            if any(school.lower() in affil_lower for school in elite_us_business):
                                tier_descriptor = "top"
                            elif any(school.lower() in affil_lower for school in first_us_business):
                                tier_descriptor = "1st tier"
                            else:
                                tier_descriptor = "[2nd tier (21-50), 3rd tier (50 and under), unranked, European (including UK), non-US, top European (Oxford or Cambridge), top non-US]"
                            
                        author_descriptions.append(
                            f"{name} is a {status} {field} professor at a {tier_descriptor} university ({affil_clean})"
                        )
                    
                authors_line = "; ".join(author_descriptions)
                
            else:
                authors_line = ""    

        draft_body = f"""
           <div style="font-family: Georgia, Times, 'Times New Roman', serif; font-size: 12px;">
           <ul style="margin: 0; padding-left: 20px;">
               <li>{authors_line}</li>
               <li>Within our core scope - [add description of paper topic]</li>
               <li>Forthcoming - {paper.get('journal') if paper.get('journal') else 'unpublished working paper - '}</li>
               <li>Recommend featuring / skipping - brief description</li>
            </ul>
            </div>
        """
        with st.expander("📧 Draft Email to Editors (click to view/close)", expanded=True):
            st.markdown("**To:** <forumeditors@corpgov.law.harvard.edu>  \n"
                        "**Cc:** <bebchuk@law.harvard.edu>; "
                        "<kastiel@tauex.tau.ac.il>; "
                        "<atoniolo@corpgov.law.harvard.edu>")
            st.markdown(f"**Subject:** {subject}")

            if st.session_state.get("manual_email_edit"):
                current_text = st.session_state.get("manual_email_text") or draft_body
                new_text = st.text_area("Edit Email Body", value=current_text, height=300, key="editable_text_area")
                if st.button("Save and Exit", key="save_manual_email_text"):
                    st.session_state["manual_email_text"] = new_text
                    st.session_state["manual_email_edit"] = False
                    st.rerun()
            else:
                st.markdown(st.session_state.get("manual_email_text") or draft_body, unsafe_allow_html=True)
            
            col_a, col_b = st.columns([1, 1])
            with col_a:
                if st.button("Dismiss Email Draft", key="dismiss_email_button"):
                    st.session_state["show_email_draft"] = False
                    st.session_state["draft_paper_data"] = None
                    st.session_state["manual_email_edit"] = False
                    st.session_state["manual_email_text"] = ""
                    st.rerun()
            with col_b:
                if st.button("Edit Email Draft", key="edit_email_button"):
                    st.session_state["manual_email_edit"] = True
                    st.rerun()
            
    
    col1, col2, col3 = st.columns([2, 2, 2])

    with col1:
        st.header("New Papers")
        # sort session-state list into the three tiers you want
        if st.button("Decline ALL New Papers"):
            for paper in st.session_state["papers_to_show"]:
                append_declined(
                    paper["title"],
                    paper.get("authors", [])
                )
            st.session_state["papers_to_show"] = []
            st.success("All visible papers moved to Declined.")
            st.rerun()

        def paper_is_solicitable(paper):
            for author in paper.get('authors', []):
                if normalize_simple_firstlast(author) in solicitable_author_simple:
                    return True
            return False

        def paper_sort_key(paper):
            solicitable = paper_is_solicitable(paper)
            pending = bool(paper.get("journal")) and "forthcoming" in paper["journal"].lower()
            if solicitable:
                return (0, paper.get("title", ""))
            elif pending:
                return (1, paper.get("title", ""))
            else:
                return (2, paper.get("title", ""))

        st.session_state["papers_to_show"].sort(key=paper_sort_key)
        papers = st.session_state["papers_to_show"]
        papers = sorted(papers, key=paper_sort_key)

        if not papers:
            st.info("No new papers to display.")
        else:
            for idx, paper in enumerate(papers[:]):
                paper_id = generate_paper_id(paper['title'], paper['authors'][0] if paper.get('authors') else "")
                is_highlighted = paper_is_solicitable(paper)
                star = "⭐ " if is_highlighted else ""
                escaped_title = escape_angle_brackets(paper['title'])
                journal_str = escape_angle_brackets(paper.get('journal') or "")
                clean_authors = [escape_angle_brackets(remove_downloads_trailer(a)) for a in paper.get('authors', []) if a]
                clean_affils = [escape_angle_brackets(remove_downloads_trailer(a)) for a in paper.get('affiliations', []) if a]
                authors_line = " | ".join(clean_authors)
                affiliations_line = " | ".join(clean_affils)
                if is_highlighted:
                    bg_color = "#FFF7CC"
                    border_color = "#FFD700"
                else:
                    bg_color = "#D1E7DD"
                    border_color = "#198754"
                html = f"""
                        <div style="background-color:{bg_color}; border-left:6px solid {border_color}; padding: 12px 16px 8px 16px; border-radius: 8px; margin-bottom:10px">
                            <span style="color:#0A3622; font-weight:bold;">{star}{escaped_title}</span><br>
                            <span style="color:#555;">{journal_str}</span><br>
                            <span style="color:#0A3622;">{authors_line}</span><br>
                            <span style="color:#666;">{affiliations_line}</span>
                        </div>
                    """
                st.markdown(html, unsafe_allow_html=True)

                col_decline, col_option = st.columns([1, 1])
                decline_key = f"decline_{paper_id}"
                option_key = f"option_{paper_id}"

                with col_decline:
                    if st.button("Decline", key=decline_key):
                        append_declined(paper['title'], paper.get("authors", []))
                        st.session_state["papers_to_show"].pop(idx)
                        st.rerun()
                with col_option:
                    if st.button("Option", key=option_key):
                        append_optioned(
                            paper['title'],
                            paper.get('authors', []),
                            paper.get('affiliations', []),
                            paper.get('journal', "")
                        )
                        # move it into column 2 for this session
                        st.session_state["optioned_papers"].append(paper)
                        st.session_state["papers_to_show"].pop(idx)
                       # Prepare email draft data for the expander at the top
                        st.session_state["show_email_draft"] = True
                        st.session_state["draft_paper_data"] = {
                            "title": paper["title"],
                            "authors": paper.get("authors", []),
                            "journal": paper.get("journal", ""),
                            "affiliations": paper.get("affiliations", [])
                        }
                        st.rerun()
                st.markdown("---")

    with col2:
        st.header("Options")
        optioned = st.session_state["optioned_papers"]
        if not optioned:
            st.write("No papers have been optioned yet.")
        else:
            for idx, paper in enumerate(optioned):
                escaped_title = escape_angle_brackets(paper['title'])
                clean_authors = [escape_angle_brackets(remove_downloads_trailer(a)) for a in paper.get('authors', []) if a]
                clean_affils = [escape_angle_brackets(remove_downloads_trailer(a)) for a in paper.get('affiliations', []) if a]
                authors_line = " | ".join(clean_authors)
                affiliations_line = " | ".join(clean_affils)
                st.markdown(f"**{escaped_title}**")
                journal_str = escape_angle_brackets(paper.get('journal') or "")
                if journal_str:
                    st.markdown(f"*{journal_str}*")
                st.write(authors_line)
                if affiliations_line:
                    st.write(affiliations_line)
                col_decline, col_solicit = st.columns([1, 1])
                decline_key = f"decline_option_{idx}_{paper['title']}"
                solicit_key = f"solicit_{idx}_{paper['title']}"
                with col_decline:
                    if st.button("Decline", key=decline_key):
                        append_declined(paper['title'], paper.get("authors", []))
                        remove_optioned(paper['title'], paper.get("authors", []))
                        st.session_state["optioned_papers"].pop(idx)
                        st.rerun()
                with col_solicit:
                    if st.button("Solicit", key=solicit_key):
                        remove_optioned(paper['title'], paper.get('authors', []))  # persistently remove from file
                        st.session_state["optioned_papers"].pop(idx)
                        st.session_state["solicited_papers"].append(paper)
                        append_solicited(
                            paper['title'],
                            paper.get('authors', []),
                            paper.get('affiliations', []),
                            paper.get('journal', "")
                        )
                        st.rerun()
                st.markdown("---")

    with col3:
        st.header("Solicitations")
        solicited = st.session_state["solicited_papers"]
        if not solicited:
            st.write("No papers have been solicited yet.")
        else:
            for idx, paper in enumerate(solicited):
                escaped_title = escape_angle_brackets(paper['title'])
                clean_authors = [escape_angle_brackets(remove_downloads_trailer(a)) for a in paper.get('authors', []) if
                                 a]
                st.markdown(f"**{escaped_title}**")
                st.write(" and ".join(clean_authors))
                st.markdown("---")

                col_accept, col_decline = st.columns([1, 1])
                accept_key = f"accept_solicited_{idx}_{paper['title']}"
                decline_key = f"decline_solicited_{idx}_{paper['title']}"

                with col_accept:
                    if st.button("Accept", key=accept_key):
                        append_solicited_accepted(
                            paper['title'],
                            paper.get('authors', []),
                            paper.get('affiliations', []),
                            paper.get('journal', "")
                        )
                        remove_solicited(paper['title'], paper.get('authors', []))  # persistently remove from file
                        st.session_state["solicited_papers"].pop(idx)
                        st.rerun()

                with col_decline:
                    if st.button("Decline", key=decline_key):
                        append_solicited_declined(
                            paper['title'],
                            paper.get('authors', []),
                            paper.get('affiliations', []),
                            paper.get('journal', "")
                        )
                        remove_solicited(paper['title'], paper.get('authors', []))  # persistently remove from file
                        st.session_state["solicited_papers"].pop(idx)
                        st.rerun()

elif page == "Declined Papers":
    st.title("Declined Papers")

    if os.path.exists(declined_filename):
        with open(declined_filename, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                st.info("No declined papers found.")
            else:
                for row in rows:
                    title = escape_angle_brackets(row.get('title', ''))
                    authors = row.get('authors', '')
                    clean_authors = [escape_angle_brackets(a.strip()) for a in authors.split(';') if a.strip()]
                    authors_line = " | ".join(clean_authors)
                    st.markdown(f"**{title}**")
                    st.write(authors_line)
                    st.markdown("---")
    else:
        st.info("No declined papers file found.")
