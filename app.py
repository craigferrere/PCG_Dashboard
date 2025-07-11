import streamlit as st
import imaplib
import email
import re
import csv
import os
import unicodedata
import hashlib
import json
from datetime import datetime
import pandas as pd

# Set page config first!
st.set_page_config(
    page_title="PCG Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== PASSWORD AUTHENTICATION ==========

def check_password():
    def password_entered():
        if st.session_state.get("password") == "7bpsBG6vJz":
            st.session_state["authenticated"] = True
            del st.session_state["password"]
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

# ========== CONSTANTS ==========

MASTER_CSV = "papers_master.csv"
EMAIL_CACHE_FILE = "email_cache.json"
EMAIL_IDS_FILE = "processed_email_ids.txt"

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

def generate_paper_id(title, first_author):
    norm_title = normalize_title(title)
    norm_author = normalize_simple_firstlast(first_author)
    combined = norm_title + norm_author
    return hashlib.md5(combined.encode('utf-8')).hexdigest()

# ========== MASTER CSV MANAGEMENT ==========

def initialize_master_csv():
    """Initialize the master CSV file if it doesn't exist"""
    if not os.path.exists(MASTER_CSV):
        columns = [
            'paper_id', 'title', 'first_author', 'authors', 'journal', 'affiliations',
            'norm_title', 'norm_first_author', 'status', 'date_added', 'date_updated'
        ]
        df = pd.DataFrame(columns=columns)
        df.to_csv(MASTER_CSV, index=False)
        return df
    return pd.read_csv(MASTER_CSV)

def add_paper_to_master(paper_data, status):
    """Add or update a paper in the master CSV"""
    df = initialize_master_csv()
    
    # Generate paper ID
    first_author = paper_data.get('authors', [''])[0] if paper_data.get('authors') else ""
    paper_id = generate_paper_id(paper_data['title'], first_author)
    
    # Check if paper already exists
    existing = df[df['paper_id'] == paper_id]
    
    if existing.empty:
        # Add new paper
        new_row = {
            'paper_id': paper_id,
            'title': paper_data['title'],
            'first_author': first_author,
            'authors': '; '.join(paper_data.get('authors', [])),
            'journal': paper_data.get('journal', ''),
            'affiliations': '; '.join(paper_data.get('affiliations', [])),
            'norm_title': normalize_title(paper_data['title']),
            'norm_first_author': normalize_simple_firstlast(first_author),
            'status': status,
            'date_added': datetime.now().isoformat(),
            'date_updated': datetime.now().isoformat()
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    else:
        # Update existing paper status
        df.loc[df['paper_id'] == paper_id, 'status'] = status
        df.loc[df['paper_id'] == paper_id, 'date_updated'] = datetime.now().isoformat()
    
    df.to_csv(MASTER_CSV, index=False)
    return paper_id

def get_papers_by_status(status):
    """Get papers by status from master CSV only (no fallback to old CSVs)"""
    if not os.path.exists(MASTER_CSV):
        return []
    df = pd.read_csv(MASTER_CSV)
    papers = df[df['status'] == status].to_dict('records')
    result = []
    for paper in papers:
        result.append({
            'title': paper['title'],
            'authors': [a.strip() for a in paper['authors'].split(';') if a.strip()],
            'affiliations': [a.strip() for a in paper['affiliations'].split(';') if a.strip()],
            'journal': paper['journal']
        })
    return result

def get_all_paper_ids_by_status(status):
    """Get all paper IDs for a given status"""
    if not os.path.exists(MASTER_CSV):
        return set()
    
    df = pd.read_csv(MASTER_CSV)
    return set(df[df['status'] == status]['paper_id'].tolist())

# ========== EMAIL CACHING ==========

def load_email_cache():
    """Load cached email data"""
    if os.path.exists(EMAIL_CACHE_FILE):
        try:
            with open(EMAIL_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_email_cache(cache_data):
    """Save email cache to file"""
    with open(EMAIL_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

def get_processed_email_ids():
    """Get list of already processed email IDs"""
    if os.path.exists(EMAIL_IDS_FILE):
        with open(EMAIL_IDS_FILE, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_processed_email_id(email_id):
    """Save processed email ID"""
    with open(EMAIL_IDS_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{email_id}\n")

def process_and_store_new_papers():
    emails = fetch_and_cache_emails()
    df = initialize_master_csv()
    existing_ids = set(df['paper_id']) if not df.empty else set()
    for email in emails:
        for paper in extract_papers_from_body(email["body"]):
            first_author = paper.get('authors', [''])[0] if paper.get('authors') else ""
            paper_id = generate_paper_id(paper['title'], first_author)
            if paper_id not in existing_ids:
                add_paper_to_master(paper, 'new')

# ========== IMPROVED AUTHOR/AFFILIATION SPLITTING ==========

def split_authors(authors_line):
    authors_line = authors_line.strip()
    if ' and ' in authors_line:
        pre_and, after_and = authors_line.rsplit(' and ', 1)
        tokens = after_and.split()
        # If the second token is a letter and period, last author is next three tokens
        if len(tokens) >= 3 and re.match(r'^[A-Z]\.$', tokens[1]):
            last_author = ' '.join(tokens[:3])
            rest = tokens[3:]
        else:
            last_author = ' '.join(tokens[:2])
            rest = tokens[2:]
        # Left side: split by comma for previous authors
        authors = [a.strip() for a in pre_and.split(',') if a.strip()]
        authors.append(last_author.strip())
        return authors
    else:
        return [a.strip() for a in authors_line.split(',') if a.strip()]

def split_affiliations(authors_line, affil_line):
    # Find the last author in the authors_line
    if ' and ' in authors_line:
        pre_and, after_and = authors_line.rsplit(' and ', 1)
        tokens = after_and.split()
        if len(tokens) >= 3 and re.match(r'^[A-Z]\.$', tokens[1]):
            last_author = ' '.join(tokens[:3])
            rest = tokens[3:]
        else:
            last_author = ' '.join(tokens[:2])
            rest = tokens[2:]
        # The affiliation is everything after the last author and before the next comma
        affil_text = ' '.join(rest) + ' ' + affil_line if affil_line else ' '.join(rest)
        affil_text = affil_text.strip()
        # Split affiliations by comma
        affiliations = [a.strip() for a in affil_text.split(',') if a.strip()]
        return affiliations
    else:
        return [a.strip() for a in affil_line.split(',') if a.strip()] if affil_line else []

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

# ========== LEGACY FUNCTIONS (keeping for compatibility) ==========

def collapse_multiline_titles(text):
    lines = text.split('\n')
    collapsed = []
    i = 0
    while i < len(lines):
        if re.match(r"^\s*\d+\.\s*$", lines[i]):
            i += 1
            title_lines = []
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
            while j < len(lines) and not lines[j].strip():
                new_lines.append(lines[j])
                j += 1
            if j < len(lines) and lines[j].startswith("# Publication:"):
                new_lines.append(lines[j])
                j += 1
                while j < len(lines) and not lines[j].strip():
                    new_lines.append(lines[j])
                    j += 1
            if j < len(lines) and not lines[j].startswith("#"):
                new_lines.append("# Authors: " + lines[j])
                j += 1
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
            block = [line.replace("# Authors:", "").strip()]
            i += 1
            blank_seen = False

            while i < len(lines):
                current = lines[i].strip()
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
    affiliation_keywords = {'University', 'School', 'College', 'Institute', 'Center', 'Faculty', 'Department'}
    debug_info = []
    
    for line in lines:
        if line.startswith("# Author:"):
            content = line[len("# Author:"):].strip()
            debug_info.append(f"Processing: '{content}'")
            
            if ' and ' not in content and ',' not in content:
                tokens = content.split()
                if len(tokens) >= 4:
                    for i in range(2, min(5, len(tokens))):
                        name = " ".join(tokens[:i])
                        remainder = " ".join(tokens[i:])
                        if any(word in affiliation_keywords for word in remainder.split()):
                            new_lines.append("# Author: " + name)
                            new_lines.append("# Affiliation: " + remainder)
                            debug_info.append(f"Single author split: '{name}' | '{remainder}'")
                            break
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
                continue
            and_index = content.find(" and ")
            if and_index == -1:
                new_lines.append(line)
                continue
            before_and = content[:and_index]
            after_and = content[and_index + len(" and "):].strip()
            debug_info.append(f"Before 'and': '{before_and}' | After 'and': '{after_and}'")

            # Split into tokens to analyze the structure
            tokens = after_and.split()
            debug_info.append(f"Tokens after 'and': {tokens}")
            
            if len(tokens) >= 3:
                # Check if second token is a middle initial (letter + period)
                if re.match(r'^[A-Z]\.$', tokens[1]):
                    # Middle initial case: take exactly 3 tokens for last author
                    last_author = " ".join(tokens[:3])
                    affiliations = " ".join(tokens[3:])
                    debug_info.append(f"Middle initial detected. Last author: '{last_author}' | Affiliations: '{affiliations}'")
                else:
                    # No middle initial: take first 2 tokens for last author
                    last_author = " ".join(tokens[:2])
                    affiliations = " ".join(tokens[2:])
                    debug_info.append(f"No middle initial. Last author: '{last_author}' | Affiliations: '{affiliations}'")
                
                new_lines.append("# Author: " + before_and.strip() + " and " + last_author)
                if affiliations.strip():
                    new_lines.append("# Affiliation: " + affiliations.strip())
                continue
            else:
                # Fallback for short names
                new_lines.append(line)
                 
        else:
            new_lines.append(line)
    
    # Store debug info in session state for display
    if debug_info:
        st.session_state["debug_author_splitting"] = debug_info
    
    return "\n".join(new_lines)

def split_and_comma_list(line):
    # Split on commas, then split the last element on ' and '
    if not line:
        return []
    
    # Add debug output
    if "debug_author_splitting" in st.session_state:
        st.session_state["debug_author_splitting"].append(f"split_and_comma_list input: '{line}'")
    
    parts = [p.strip() for p in line.split(',') if p.strip()]
    if parts and ' and ' in parts[-1]:
        before_and, after_and = parts[-1].rsplit(' and ', 1)
        before_and = before_and.strip()
        after_and = after_and.strip()
        
        # Add debug output
        if "debug_author_splitting" in st.session_state:
            st.session_state["debug_author_splitting"].append(f"split_and_comma_list: before_and='{before_and}' after_and='{after_and}'")
        
        # Handle middle initials in the last author
        tokens = after_and.split()
        if len(tokens) >= 3 and re.match(r'^[A-Z]\.$', tokens[1]):
            # Middle initial case: take exactly 3 tokens for last author
            last_author = ' '.join(tokens[:3])
            if "debug_author_splitting" in st.session_state:
                st.session_state["debug_author_splitting"].append(f"split_and_comma_list: MIDDLE INITIAL detected, last_author='{last_author}'")
        else:
            # No middle initial: take first 2 tokens for last author
            last_author = ' '.join(tokens[:2]) if len(tokens) >= 2 else after_and
            if "debug_author_splitting" in st.session_state:
                st.session_state["debug_author_splitting"].append(f"split_and_comma_list: no middle initial, last_author='{last_author}'")
        
        new_parts = []
        if before_and:
            new_parts.append(before_and)
        if last_author:
            new_parts.append(last_author)
        parts = parts[:-1] + new_parts
    
    if "debug_author_splitting" in st.session_state:
        st.session_state["debug_author_splitting"].append(f"split_and_comma_list output: {parts}")
    
    return parts

def extract_papers_from_body(text):
    lines = text.strip().splitlines()
    papers = []
    title = None
    journal = None
    authors_line = None
    affils_line = None
    
    # Add debug output
    if "debug_author_splitting" in st.session_state:
        st.session_state["debug_author_splitting"].append("=== extract_papers_from_body ===")
    
    for line in lines:
        line = line.strip()
        if line.startswith("# Title:"):
            if title and authors_line:
                if "debug_author_splitting" in st.session_state:
                    st.session_state["debug_author_splitting"].append(f"Processing paper: title='{title}' authors_line='{authors_line}'")
                authors = split_and_comma_list(authors_line)
                affiliations = split_and_comma_list(affils_line) if affils_line else [""] * len(authors)
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
            title = line[len("# Title:"):].strip()
            journal = None
            authors_line = None
            affils_line = None
        elif line.startswith("# Publication:"):
            journal = line[len("# Publication:"):].strip()
        elif line.startswith("# Author:") or line.startswith("# Authors:"):
            authors_line = line.split(":", 1)[1].strip()
            if "debug_author_splitting" in st.session_state:
                st.session_state["debug_author_splitting"].append(f"Found author line: '{authors_line}'")
        elif line.startswith("# Affiliation:") or line.startswith("# Affiliations:"):
            affils_line = line.split(":", 1)[1].strip()
            if "debug_author_splitting" in st.session_state:
                st.session_state["debug_author_splitting"].append(f"Found affiliation line: '{affils_line}'")
    if title and authors_line:
        if "debug_author_splitting" in st.session_state:
            st.session_state["debug_author_splitting"].append(f"Processing final paper: title='{title}' authors_line='{authors_line}'")
        authors = split_and_comma_list(authors_line)
        affiliations = split_and_comma_list(affils_line) if affils_line else [""] * len(authors)
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

# ========== IMPROVED EMAIL PROCESSING ==========

def fetch_and_cache_emails():
    """Fetch emails and cache them for better performance"""
    cache = load_email_cache()
    processed_ids = get_processed_email_ids()
    
    # Check if we have recent cache (within last hour)
    if cache.get('last_updated'):
        last_updated = datetime.fromisoformat(cache['last_updated'])
        if (datetime.now() - last_updated).seconds < 3600:  # 1 hour
            return cache.get('emails', [])
    
    imap_host = "imap.gmail.com"
    username = "PCGssrn@gmail.com"
    app_password = "lbcf ioir uuoy wqui"
    
    try:
        print("Connecting to Gmail...")
        mail = imaplib.IMAP4_SSL(imap_host)
        mail.login(username, app_password)
        print("Login successful.")
        
        mail.select("INBOX")
        status, message_numbers = mail.search(None, "ALL")
        
        if status != "OK":
            print("No emails found.")
            mail.logout()
            return cache.get('emails', [])
        
        emails = []
        for num in message_numbers[0].split():
            try:
                status, msg_data = mail.fetch(num, '(RFC822)')
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        email_id = msg.get('Message-ID', str(num))
                        
                        # Skip if already processed
                        if email_id in processed_ids:
                            continue
                        
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain" and part.get("Content-Disposition") is None:
                                    charset = part.get_content_charset() or "utf-8"
                                    body += part.get_payload(decode=True).decode(charset, errors="ignore")
                        else:
                            charset = msg.get_content_charset() or "utf-8"
                            body = msg.get_payload(decode=True).decode(charset, errors="ignore")
                        
                        # Clean the body
                        body = clean_email_body(body)
                        
                        emails.append({
                            "body": body.strip(),
                            "email_id": email_id
                        })
                        
                        # Mark as processed
                        save_processed_email_id(email_id)
                        
            except Exception as e:
                print(f"Error processing email {num}: {e}")
                continue
        
        mail.logout()
        
        # Update cache
        cache['emails'] = emails
        cache['last_updated'] = datetime.now().isoformat()
        save_email_cache(cache)
        
        print(f"Fetched {len(emails)} new emails.")
        return emails
        
    except Exception as e:
        print(f"Error connecting to email: {e}")
        return cache.get('emails', [])

def clean_email_body(body):
    """Clean email body with improved regex patterns"""
    # Remove HTML tags
    body = re.sub(r"<[^>]+>", "", body)
    
    # Remove metadata lines
    patterns_to_remove = [
        r"^Number of pages: \d+\s+Posted: \d{1,2} [A-Z][a-z]{2} 202\d(?:\s+Last Revised: \d{1,2} [A-Z][a-z]{2} 202\d)?\s*$",
        r"^Posted: \d{1,2} [A-Z][a-z]{2} 202\d\s*$",
        r"^Downloads\d+\s*$",
        r"^(Fiduciary|Shareholder|Hedge Funds|Mutual Funds|ESG|Institutional Investors|Corporate|Stakeholder|Merger|Directors|Compensation|Securities|SPAC|Proxy Advisors)\s*$",
        r"^Keywords:.*\n(?:^[^\S\r\n]*\S.*\n)?",
        r"^Body preview:\s*$",
        r"\[image: Multiple version icon\]There are \d+ versions of this paper",
        r"\*affiliation\s+(?:not\s+provided\s+to\s+SSRN)\*",
    ]
    
    for pattern in patterns_to_remove:
        body = re.sub(pattern, "", body, flags=re.MULTILINE | re.IGNORECASE)
    
    # Replace affiliation placeholders
    body = body.replace("*affiliation not provided to SSRN*", "No affiliation")
    
    # Process publication markers
    body = re.sub(
        r"\*(.*?)\n(.*?)\*\s*",
        lambda m: f"# Publication: {m.group(1).strip()} {m.group(2).strip()}\n\n",
        body
    )
    body = re.sub(
        r"\*(.*?)\*\s*",
        lambda m: f"# Publication: {m.group(1).strip()}\n\n",
        body
    )
    
    # Clean up whitespace
    body = re.sub(r'(\n\s*){2,}', '\n\n', body)
    
    # Process the text through the pipeline
    body = collapse_multiline_titles(body)
    body = tag_author_lines(body)
    body = flatten_author_blocks(body)
    body = split_authors_affiliations(body)
    
    return body

# ========== MAIN DATA LOADING ==========

def get_all_papers_filtered():
    """Get all papers filtered by status"""
    try:
        emails = fetch_and_cache_emails()
        st.write(f"Fetched {len(emails)} emails from inbox.")
        declined_ids = get_all_paper_ids_by_status('declined')
        optioned_ids = get_all_paper_ids_by_status('optioned')
        solicited_ids = get_all_paper_ids_by_status('solicited')
        
        new_papers = []
        
        for email in emails:
            try:
                extracted_papers = extract_papers_from_body(email["body"])
                st.write(f"DEBUG: Extracted {len(extracted_papers)} papers from email")
                for paper in extracted_papers:
                    try:
                        authors = paper.get("authors", [])
                        st.write(f"DEBUG: Paper authors: {authors}")
                        first_author = ""
                        if isinstance(authors, list) and len(authors) > 0 and authors[0]:
                            first_author = str(authors[0])
                        
                        title = paper.get("title", "")
                        if not title:  # Skip papers without titles
                            continue
                            
                        pid = generate_paper_id(title, first_author)
                        # Skip if already declined, optioned, or solicited
                        if pid in declined_ids or pid in optioned_ids or pid in solicited_ids:
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

# ========== LOAD SOLICITABLE AUTHORS ==========

solicitable_author_simple = set()
try:
    with open('solicitable_authors.csv', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        header = reader.fieldnames[0]
        for row in reader:
            fullname = row.get(header, '').strip()
            norm = normalize_simple_firstlast(fullname)
            if norm:
                solicitable_author_simple.add(norm)
except Exception as e:
    st.error(f"Error loading solicitable authors: {e}")

# ========== UTILITY FUNCTIONS FOR UI ==========

def escape_angle_brackets(text):
    if not text:
        return ""
    return text.replace('<', '&lt;').replace('>', '&gt;')

def remove_downloads_trailer(text):
    text = re.sub(r'(,)?\s*Downloads,?\s*\d+\s*$', '', text).strip()
    text = re.sub(r',\s*\d+\s*$', '', text).strip()
    text = re.sub(r'(?:,|\band\b)?\s*\d+\s*$', '', text).strip()
    return text


# ========== SESSION STATE INITIALIZATION ==========

if "papers_to_show" not in st.session_state:
    st.session_state["papers_to_show"] = get_all_papers_filtered()

if "optioned_papers" not in st.session_state:
    st.session_state["optioned_papers"] = get_papers_by_status('optioned')

if "solicited_papers" not in st.session_state:
    st.session_state["solicited_papers"] = get_papers_by_status('solicited')

if "show_email_draft" not in st.session_state:
    st.session_state["show_email_draft"] = False
if "draft_paper_data" not in st.session_state:
    st.session_state["draft_paper_data"] = None
if "manual_email_edit" not in st.session_state:
    st.session_state["manual_email_edit"] = False
if "manual_email_text" not in st.session_state:
    st.session_state["manual_email_text"] = ""

# ========== UI ==========

st.sidebar.title("PCG Dashboard")
st.sidebar.image("harvard.png", width=120)

# Add refresh button
if st.sidebar.button("🔄 Refresh Papers"):
    st.session_state["papers_to_show"] = get_papers_by_status('new')
    st.session_state["optioned_papers"] = get_papers_by_status('optioned')
    st.session_state["solicited_papers"] = get_papers_by_status('solicited')
    st.rerun()

if st.sidebar.button("Clear Email Cache"):
    if os.path.exists("email_cache.json"):
        os.remove("email_cache.json")
        st.success("Email cache cleared! Please refresh the app.")
    else:
        st.info("No cache file found.")

if st.sidebar.button("Clear Processed Email IDs"):
    if os.path.exists("processed_email_ids.txt"):
        os.remove("processed_email_ids.txt")
        st.success("Processed email IDs cleared! Please refresh the app.")
    else:
        st.info("No processed email IDs file found.")

# Debug section
if st.sidebar.checkbox("Show Debug Info"):
    if "debug_author_splitting" in st.session_state:
        st.sidebar.markdown("### Debug: Author Splitting")
        for debug_line in st.session_state["debug_author_splitting"]:
            st.sidebar.text(debug_line)
    else:
        st.sidebar.text("No debug info available")

# Force debug processing
if st.sidebar.button("🔍 Force Debug Processing"):
    # Clear any existing debug info
    if "debug_author_splitting" in st.session_state:
        del st.session_state["debug_author_splitting"]
    
    # Force email processing to trigger debug
    emails = fetch_and_cache_emails()
    if emails:
        # Process the first email to generate debug info
        body = emails[0]["body"]
        processed_body = split_authors_affiliations(body)
        st.sidebar.success("Debug processing completed. Check debug info above.")
    else:
        st.sidebar.warning("No emails found to process.")

page = st.sidebar.radio(
    "Navigate",
    ["Dashboard", "Master Data"]
)

if page == "Dashboard":
    # Email draft section
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
        if st.button("Decline ALL New Papers"):
            for paper in st.session_state["papers_to_show"]:
                add_paper_to_master(paper, 'declined')
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
                        add_paper_to_master(paper, 'declined')
                        st.session_state["papers_to_show"].pop(idx)
                        st.rerun()
                with col_option:
                    if st.button("Option", key=option_key):
                        add_paper_to_master(paper, 'optioned')
                        st.session_state["optioned_papers"].append(paper)
                        st.session_state["papers_to_show"].pop(idx)
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
                        add_paper_to_master(paper, 'declined')
                        st.session_state["optioned_papers"].pop(idx)
                        st.rerun()
                with col_solicit:
                    if st.button("Solicit", key=solicit_key):
                        add_paper_to_master(paper, 'solicited')
                        st.session_state["optioned_papers"].pop(idx)
                        st.session_state["solicited_papers"].append(paper)
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
                clean_authors = [escape_angle_brackets(remove_downloads_trailer(a)) for a in paper.get('authors', []) if a]
                st.markdown(f"**{escaped_title}**")
                st.write(" and ".join(clean_authors))
                st.markdown("---")

                col_accept, col_decline = st.columns([1, 1])
                accept_key = f"accept_solicited_{idx}_{paper['title']}"
                decline_key = f"decline_solicited_{idx}_{paper['title']}"

                with col_accept:
                    if st.button("Accept", key=accept_key):
                        add_paper_to_master(paper, 'accepted')
                        st.session_state["solicited_papers"].pop(idx)
                        st.rerun()

                with col_decline:
                    if st.button("Decline", key=decline_key):
                        add_paper_to_master(paper, 'declined')
                        st.session_state["solicited_papers"].pop(idx)
                        st.rerun()

elif page == "Master Data":
    st.title("Master Data Management")
    
    if os.path.exists(MASTER_CSV):
        df = pd.read_csv(MASTER_CSV)
        st.write(f"Total papers in master database: {len(df)}")
        
        # Status distribution
        status_counts = df['status'].value_counts()
        st.write("**Papers by Status:**")
        for status, count in status_counts.items():
            st.write(f"- {status}: {count}")
        
        # Show recent papers
        st.write("**Recent Papers:**")
        recent_papers = df.sort_values('date_added', ascending=False).head(10)
        for _, paper in recent_papers.iterrows():
            st.write(f"- {paper['title']} ({paper['status']})")
    else:
        st.info("No master data file found. It will be created when you first process papers.")
    
    # Add data export functionality
    if st.button("Export Master Data"):
        if os.path.exists(MASTER_CSV):
            df = pd.read_csv(MASTER_CSV)
            csv = df.to_csv(index=False)
            st.download_button(
                label="Download Master Data CSV",
                data=csv,
                file_name="papers_master_export.csv",
                mime="text/csv"
            ) 
