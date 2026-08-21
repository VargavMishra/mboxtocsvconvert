import os
import sys
import csv
import re
import json
import time
import email
from email import policy
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

class ConversionCanceledError(Exception):
    pass

class HTMLFilter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.ignore_stack = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ('style', 'script', 'head'):
            self.ignore_stack.append(tag.lower())

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in ('style', 'script', 'head'):
            if tag_lower in self.ignore_stack:
                self.ignore_stack.remove(tag_lower)

    def handle_data(self, data):
        if not self.ignore_stack:
            self.text.append(data)

    def get_text(self):
        return "".join(self.text)

def strip_html(html_content):
    if not html_content:
        return ""
    try:
        parser = HTMLFilter()
        parser.feed(html_content)
        return parser.get_text()
    except Exception:
        clean = re.sub(r'<(style|script|head)[^>]*>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        return re.sub(r'<[^>]+>', ' ', clean)

def extract_mbox_message_data(msg_bytes):
    try:
        msg = email.message_from_bytes(msg_bytes, policy=policy.default)
    except Exception:
        try:
            msg = email.message_from_bytes(msg_bytes, policy=policy.compat32)
        except Exception:
            return None

    date_val = str(msg.get('Date', '') or '')
    from_val = str(msg.get('From', '') or '')
    to_val = str(msg.get('To', '') or '')
    cc_val = str(msg.get('Cc', '') or '')
    bcc_val = str(msg.get('Bcc', '') or '')
    subject_val = str(msg.get('Subject', '') or '')
    thread_id = str(msg.get('X-GM-THRID', '') or '')
    labels = str(msg.get('X-Gmail-Labels', '') or '')
    msg_id = str(msg.get('Message-ID', '') or '')

    plain_text_parts = []
    html_text_parts = []
    attachment_names = []

    if msg.is_multipart():
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            filename = part.get_filename()

            if filename or "attachment" in content_disposition:
                if filename:
                    attachment_names.append(filename)
                else:
                    attachment_names.append("unnamed_attachment")
                continue

            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    payload = part.get_content()
                    if isinstance(payload, str):
                        plain_text_parts.append(payload)
                except Exception:
                    payload = part.get_payload(decode=True)
                    if payload:
                        plain_text_parts.append(payload.decode('utf-8', errors='replace'))
            elif content_type == "text/html":
                try:
                    payload = part.get_content()
                    if isinstance(payload, str):
                        html_text_parts.append(payload)
                except Exception:
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_text_parts.append(payload.decode('utf-8', errors='replace'))
    else:
        content_type = msg.get_content_type()
        try:
            payload = msg.get_content()
            if isinstance(payload, str):
                if content_type == "text/html":
                    html_text_parts.append(payload)
                else:
                    plain_text_parts.append(payload)
        except Exception:
            payload = msg.get_payload(decode=True)
            if payload:
                text = payload.decode('utf-8', errors='replace')
                if content_type == "text/html":
                    html_text_parts.append(text)
                else:
                    plain_text_parts.append(text)

    body = ""
    if plain_text_parts:
        body = "\n".join(plain_text_parts)
    elif html_text_parts:
        body = strip_html("\n".join(html_text_parts))

    body = body.replace('\x00', '')
    lines = [line.strip() for line in body.splitlines()]
    body_clean = "\n".join([l for l in lines if l])
    snippet = body_clean[:200].replace('\n', ' ')

    return {
        "Date": date_val,
        "From": from_val,
        "To": to_val,
        "Cc": cc_val,
        "Bcc": bcc_val,
        "Subject": subject_val,
        "Thread-ID": thread_id,
        "Labels": labels,
        "Message-ID": msg_id,
        "Has-Attachments": "Yes" if attachment_names else "No",
        "Attachment-Names": "; ".join(attachment_names),
        "Snippet": snippet,
        "Body": body_clean
    }

def convert_mbox(input_path, output_path, progress_cb=None):
    file_size = os.path.getsize(input_path)
    fieldnames = [
        "Date", "From", "To", "Cc", "Bcc", "Subject",
        "Thread-ID", "Labels", "Message-ID",
        "Has-Attachments", "Attachment-Names", "Snippet", "Body"
    ]

    count = 0
    bytes_read = 0

    with open(output_path, 'w', newline='', encoding='utf-8-sig', errors='replace') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        with open(input_path, 'rb') as f:
            current_msg_lines = []
            
            for line in f:
                bytes_read += len(line)
                if line.startswith(b'From ') and current_msg_lines:
                    msg_bytes = b''.join(current_msg_lines)
                    row = extract_mbox_message_data(msg_bytes)
                    if row:
                        writer.writerow(row)
                        count += 1

                    current_msg_lines = [line]

                    if progress_cb and count % 200 == 0:
                        pct = min(99.0, (bytes_read / file_size) * 100) if file_size > 0 else 50.0
                        res = progress_cb(pct, f"Processed {count} emails...")
                        if res is False:
                            raise ConversionCanceledError("Conversion canceled by user.")
                else:
                    current_msg_lines.append(line)

            if current_msg_lines:
                msg_bytes = b''.join(current_msg_lines)
                row = extract_mbox_message_data(msg_bytes)
                if row:
                    writer.writerow(row)
                    count += 1

    if progress_cb:
        progress_cb(100.0, f"Completed: {count} emails converted to CSV.")
    return count

def flatten_dict(d, parent_key='', sep='.'):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            items.append((new_key, json.dumps(v, ensure_ascii=False)))
        else:
            items.append((new_key, v))
    return dict(items)

def convert_json(input_path, output_path, progress_cb=None):
    if progress_cb:
        if progress_cb(10.0, "Reading JSON file...") is False:
            raise ConversionCanceledError("Conversion canceled by user.")

    with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read().strip()

    rows = []
    if content.startswith('['):
        try:
            data = json.loads(content)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        rows.append(flatten_dict(item))
                    else:
                        rows.append({"value": item})
        except Exception:
            pass
    
    if not rows:
        with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict):
                            rows.append(flatten_dict(item))
                        else:
                            rows.append({"value": item})
                    except Exception:
                        continue

    if not rows:
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                rows.append(flatten_dict(data))
        except Exception as e:
            raise ValueError(f"Invalid JSON content: {e}")

    if not rows:
        raise ValueError("No valid records found in JSON file.")

    if progress_cb:
        if progress_cb(50.0, "Writing CSV file...") is False:
            raise ConversionCanceledError("Conversion canceled by user.")

    fieldnames = []
    for row in rows:
        for k in row.keys():
            if k not in fieldnames:
                fieldnames.append(k)

    with open(output_path, 'w', newline='', encoding='utf-8-sig', errors='replace') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if progress_cb:
        progress_cb(100.0, f"Completed: {len(rows)} records converted.")
    return len(rows)

def convert_excel(input_path, output_path, progress_cb=None):
    if progress_cb:
        if progress_cb(20.0, "Reading Excel spreadsheet...") is False:
            raise ConversionCanceledError("Conversion canceled by user.")

    import pandas as pd
    excel_file = pd.ExcelFile(input_path)
    sheet_name = excel_file.sheet_names[0]
    
    if progress_cb:
        if progress_cb(50.0, f"Converting sheet '{sheet_name}' to CSV...") is False:
            raise ConversionCanceledError("Conversion canceled by user.")

    df = pd.read_excel(excel_file, sheet_name=sheet_name)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')

    if progress_cb:
        progress_cb(100.0, f"Completed: {len(df)} rows converted from Excel.")
    return len(df)

def convert_xml(input_path, output_path, progress_cb=None):
    if progress_cb:
        if progress_cb(20.0, "Parsing XML file...") is False:
            raise ConversionCanceledError("Conversion canceled by user.")

    tree = ET.parse(input_path)
    root = tree.getroot()

    rows = []
    for child in root:
        row = {}
        if len(child) > 0:
            for elem in child:
                row[elem.tag] = elem.text.strip() if elem.text else ""
            rows.append(row)
        else:
            rows.append({child.tag: child.text.strip() if child.text else ""})

    if not rows:
        raise ValueError("Could not extract tabular elements from XML structure.")

    fieldnames = []
    for r in rows:
        for k in r.keys():
            if k not in fieldnames:
                fieldnames.append(k)

    with open(output_path, 'w', newline='', encoding='utf-8-sig', errors='replace') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if progress_cb:
        progress_cb(100.0, f"Completed: {len(rows)} XML records converted.")
    return len(rows)

def convert_tsv(input_path, output_path, progress_cb=None):
    if progress_cb:
        if progress_cb(20.0, "Reading TSV / Delimited File...") is False:
            raise ConversionCanceledError("Conversion canceled by user.")

    count = 0
    with open(input_path, 'r', encoding='utf-8', errors='replace') as in_f:
        sample = in_f.read(4096)
        in_f.seek(0)
        delimiter = '\t' if '\t' in sample else ','

        reader = csv.reader(in_f, delimiter=delimiter)
        with open(output_path, 'w', newline='', encoding='utf-8-sig', errors='replace') as out_f:
            writer = csv.writer(out_f)
            for row in reader:
                writer.writerow(row)
                count += 1
                if progress_cb and count % 5000 == 0:
                    if progress_cb(50.0, f"Processed {count} lines...") is False:
                        raise ConversionCanceledError("Conversion canceled by user.")

    if progress_cb:
        progress_cb(100.0, f"Completed: {count} lines converted.")
    return count

def convert_file(input_path, output_path, ext, progress_cb=None):
    ext = ext.lower().strip('.')
    if ext == 'mbox':
        return convert_mbox(input_path, output_path, progress_cb)
    elif ext in ('json', 'jsonl'):
        return convert_json(input_path, output_path, progress_cb)
    elif ext in ('xlsx', 'xls'):
        return convert_excel(input_path, output_path, progress_cb)
    elif ext == 'xml':
        return convert_xml(input_path, output_path, progress_cb)
    elif ext in ('tsv', 'txt', 'csv'):
        return convert_tsv(input_path, output_path, progress_cb)
    else:
        try:
            return convert_mbox(input_path, output_path, progress_cb)
        except Exception:
            return convert_json(input_path, output_path, progress_cb)
