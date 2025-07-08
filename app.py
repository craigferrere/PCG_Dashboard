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

def fetch_all_ssrn_emails():
    imap_host = "imap.gmail.com"
    username = "PCGssrn@gmail.com"
    app_password = "lbcf ioir uuoy wqui"

    mail = imaplib.IMAP4_SSL(imap_host)
    mail.login(username, app_password)

    mail.select("INBOX")  # Select the mailbox you want to use

    # Fetch ALL emails (or adjust search filter for SSRN)
    status, message_numbers = mail.search(None, "ALL")

    emails = []
    for num in message_numbers[0].split():
        status, msg_data = mail.fetch(num, '(RFC822)')
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                subject = msg["subject"]
                if msg.is_multipart():
                    body = ""
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain" and part.get('Content-Disposition') is None:
                            body += part.get_payload(decode=True).decode(errors="ignore")
                else:
                    body = msg.get_payload(decode=True).decode(errors="ignore")
                emails.append({"subject": subject, "body": body})

    mail.logout()
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

def should_skip_line(line):
    return (
        line.startswith("Keywords:") or
        line.lower().startswith("keywords:") or
        line.strip().startswith("Downloads") or
        line.strip().lower().startswith("downloads")
    )

def split_authors(authors_line):
    authors_line = authors_line.strip()
    authors_line = re.sub(r'\s*\(\d+\)\s*$', '', authors_line)
    authors = []
    if ',' in authors_line:
        parts = [a.strip() for a in authors_line.split(',') if a.strip()]
        last = parts[-1]
        if ' and ' in last:
            and_split = [a.strip() for a in last.split(' and ') if a.strip()]
            authors.extend(parts[:-1] + and_split)
        else:
            authors.extend(parts)
    elif ' and ' in authors_line:
        authors.extend([a.strip() for a in authors_line.split(' and ') if a.strip()])
    else:
        authors.append(authors_line)
    return authors

def extract_papers_from_body(text):
    title_matches = list(re.finditer(r'^\d+\.\s+(.*)', text, re.MULTILINE))
    papers = []
    for i, m in enumerate(title_matches):
        title = remove_urls(m.group(1).strip()).rstrip('<').strip()
        seg_start = m.end()
        seg_end = title_matches[i + 1].start() if i + 1 < len(title_matches) else len(text)
        segment = text[seg_start:seg_end]
        journal = None
        lines = segment.strip().splitlines()
        for line in lines:
            if ("forthcoming" in line.lower()) and any(c.isalpha() for c in line):
                journal = line.strip()
                break
        posted_match = re.search(r'Posted:[^\n]*\n(.*)', segment, re.DOTALL)
        authors_section = ""
        if posted_match:
            authors_section = posted_match.group(1)
            authors_section = re.split(r'Number of pages:', authors_section)[0]
            authors_section = authors_section.strip()
        raw_lines = [l.strip() for l in authors_section.splitlines() if l.strip()]
        cleaned_lines = [
            remove_downloads_trailer(strip_all_hyperlinks(l))
            for l in raw_lines
            if not should_skip_line(l)
        ]
        cleaned_lines = [l for l in cleaned_lines if l]
        authors_list = []
        affiliations_list = []
        idx = 0
        while idx < len(cleaned_lines):
            split_list = split_authors(cleaned_lines[idx])
            authors_list.extend(split_list)
            affiliations_list.append(cleaned_lines[idx+1] if idx+1 < len(cleaned_lines) else "")
            idx += 2
        papers.append({
            'title': title,
            'authors': authors_list,
            'authors_lower': [a.lower() for a in authors_list],
            'affiliations': affiliations_list,
            'journal': journal,
        })
    return papers

def get_all_papers_filtered():
    try:
        emails = fetch_all_ssrn_emails()
        declined_set = read_declined_set()
        optioned_set = read_optioned_set()
        solicited_set = read_solicited_set()  # 👈 Add this line
        new_papers = []
        for email in emails:
            extracted_papers = extract_papers_from_body(email["body"])
            for paper in extracted_papers:
                first_author = paper["authors"][0] if paper.get("authors") else ""
                pid = generate_paper_id(paper["title"], first_author)
                # Skip if already declined, optioned, or solicited
                if pid in declined_set or pid in optioned_set or pid in solicited_set:  # 👈 Update this line
                    continue
                new_papers.append(paper)
        return deduplicate_papers(new_papers)
    except Exception as e:
        st.error(f"Error fetching SSRN emails: {e}")
        return []

# Move the load_solicited_papers() function definition before the session state initialization
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
            for name in last_names:
                key_status = f"status_{name}"
                key_confirm = f"confirm_{name}"

                if f"status_selected_{name}" not in st.session_state:
                    selected = st.selectbox(f"{name}'s status", status_options, key=key_status)
                    if st.button(f"Confirm {name}", key=key_confirm):
                       st.session_state[f"status_selected_{name}"] = selected
                       del st.session_state[key_status]
                    else:
                        st.markdown(f"**{name}** is marked as **{st.session_state[f'status_selected_{name}']}**.")

            if all(f"status_selected_{name}" in st.session_state for name in last_names):
                descriptor = ("law / finance prof at a [top (5), 1st tier (6-20), 2nd tier (21-50), 3rd tier (50 and under), unranked, European (including UK), non-US, top European (Oxford or Cambridge), top non-US] university (school name and country if applicable)")
            
            author_descriptions = [f"{name} is a {st.session_state[f'status_selected_{name}']} {descriptor}" 
                for name in last_names]
                if st.session_state[f'status_selected_{name}'] != "exclude"
            authors_line = ', '.join(author_descriptions)

        draft_body = f"""
           <div style="font-family: Georgia, Times, 'Times New Roman', serif; font-size: 12px;">
           <ul style="margin: 0; padding-left: 20px;">
               <li>{authors_line}</li>
               <li>Within our core scope - [add description of paper topic]</li>
               <li>Forthcoming - {paper.get('journal') if paper.get('journal') else '[Journal Name]'}</li>
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
            st.markdown(draft_body, unsafe_allow_html=True)
            if st.button("Dismiss Email Draft"):
                st.session_state["show_email_draft"] = False
                st.session_state["draft_paper_data"] = None
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
