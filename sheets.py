from googleapiclient.discovery import build
from google_auth import get_credentials


def _get_service():
    creds = get_credentials()
    return build('sheets', 'v4', credentials=creds)


def col_index_to_letter(index):
    result = ''
    while index >= 0:
        result = chr(index % 26 + ord('A')) + result
        index = index // 26 - 1
    return result


def read_main_tab(sheet_id, tab_name='Sheet1'):
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f'{tab_name}!A1:Z1000'
    ).execute()
    rows = result.get('values', [])
    if not rows:
        return {'headers': [], 'languages': [], 'rows': []}

    VALID_LANGUAGES = {'French', 'Spanish', 'German', 'Japanese', 'Russian', 'Chinese Simplified', 'Turkish'}
    headers = rows[0]
    standard_cols = headers[:4]
    languages = [h.strip() for h in headers[4:] if h.strip() in VALID_LANGUAGES]

    parsed = []
    for i, row in enumerate(rows[1:], start=2):
        key = row[0].strip() if len(row) > 0 and row[0].strip() else ''
        if not key:
            continue
        entry = {
            'row_num': i,
            'key': key,
            'type': row[1].strip() if len(row) > 1 else '',
            'context': row[2].strip() if len(row) > 2 else '',
            'english': row[3].strip() if len(row) > 3 else '',
        }
        raw_headers = rows[0]
        for j, lang in enumerate(languages):
            try:
                col_idx = raw_headers.index(lang)
            except ValueError:
                col_idx = -1
            entry[lang] = row[col_idx].strip() if col_idx >= 0 and len(row) > col_idx and row[col_idx].strip() else ''
        parsed.append(entry)

    return {'headers': headers, 'languages': languages, 'rows': parsed}


def create_translator_tab(sheet_id, tab_name, language, main_tab='Sheet1'):
    service = _get_service()
    main_data = read_main_tab(sheet_id, main_tab)

    # Create the new sheet/tab
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={
            'requests': [{
                'addSheet': {
                    'properties': {'title': tab_name}
                }
            }]
        }
    ).execute()

    # Build header + rows
    header = ['Key', 'Type', 'Context', 'English', 'Current Translation', 'Status', 'Corrected Translation', 'Suggestion']
    data_rows = []
    for row in main_data['rows']:
        data_rows.append([
            row['key'],
            row['type'],
            row['context'],
            row['english'],
            row.get(language, ''),
            'Pending',
            '',
            ''
        ])

    all_rows = [header] + data_rows
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f'{tab_name}!A1',
        valueInputOption='RAW',
        body={'values': all_rows}
    ).execute()

    return len(data_rows)


def read_translator_tab(sheet_id, tab_name):
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f'{tab_name}!A1:H1000'
    ).execute()
    rows = result.get('values', [])
    if len(rows) < 2:
        return []

    parsed = []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 1 or not row[0].strip():
            continue
        parsed.append({
            'row_num': i,
            'key': row[0].strip() if len(row) > 0 else '',
            'type': row[1].strip() if len(row) > 1 else '',
            'context': row[2].strip() if len(row) > 2 else '',
            'english': row[3].strip() if len(row) > 3 else '',
            'current': row[4].strip() if len(row) > 4 else '',
            'status': row[5].strip() if len(row) > 5 else 'Pending',
            'corrected': row[6].strip() if len(row) > 6 else '',
            'suggestion': row[7].strip() if len(row) > 7 else '',
        })
    return parsed


def _get_sheet_id(service, spreadsheet_id, tab_name):
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta['sheets']:
        if sheet['properties']['title'] == tab_name:
            return sheet['properties']['sheetId']
    return None


STATUS_COLORS = {
    'Correct': {'red': 0.85, 'green': 1.0, 'blue': 0.85, 'alpha': 1},
    'Corrected': {'red': 1.0, 'green': 0.85, 'blue': 0.85, 'alpha': 1},
    'Suggestion': {'red': 1.0, 'green': 1.0, 'blue': 0.8, 'alpha': 1},
}


def save_translation(sheet_id, tab_name, row_num, status, corrected=''):
    service = _get_service()

    # Read current translation (column E) for this row
    current_result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f'{tab_name}!E{row_num}'
    ).execute()
    current_vals = current_result.get('values', [['']])
    current_translation = current_vals[0][0] if current_vals and current_vals[0] else ''

    if status == 'Correct':
        # Copy current translation into corrected, no suggestion
        values = [[status, current_translation, '']]
    elif status == 'Suggestion':
        # Copy current translation into corrected, suggestion text in H
        values = [[status, current_translation, corrected]]
    else:
        # Corrected: translator provided the fix, no suggestion
        values = [[status, corrected, '']]

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f'{tab_name}!F{row_num}:H{row_num}',
        valueInputOption='RAW',
        body={'values': values}
    ).execute()

    color = STATUS_COLORS.get(status)
    if color:
        sid = _get_sheet_id(service, sheet_id, tab_name)
        if sid is not None:
            service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={'requests': [{
                    'repeatCell': {
                        'range': {
                            'sheetId': sid,
                            'startRowIndex': row_num - 1,
                            'endRowIndex': row_num,
                            'startColumnIndex': 5,
                            'endColumnIndex': 6
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'backgroundColor': color
                            }
                        },
                        'fields': 'userEnteredFormat.backgroundColor'
                    }
                }]}
            ).execute()


def get_new_keys(sheet_id, main_tab, translator_tab):
    main_data = read_main_tab(sheet_id, main_tab)
    translator_rows = read_translator_tab(sheet_id, translator_tab)
    existing_keys = {r['key'] for r in translator_rows}
    return [r for r in main_data['rows'] if r['key'] not in existing_keys]


def sync_new_rows(sheet_id, main_tab, translator_tab, language):
    new_rows = get_new_keys(sheet_id, main_tab, translator_tab)
    if not new_rows:
        return 0

    service = _get_service()
    data = []
    for row in new_rows:
        data.append([
            row['key'],
            row['type'],
            row['context'],
            row['english'],
            row.get(language, ''),
            'Pending',
            '',
            ''
        ])

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f'{translator_tab}!A1',
        valueInputOption='RAW',
        insertDataOption='INSERT_ROWS',
        body={'values': data}
    ).execute()

    return len(data)


def get_progress(sheet_id, tab_name):
    rows = read_translator_tab(sheet_id, tab_name)
    total = len(rows)
    reviewed = len([r for r in rows if r['status'] in ('Correct', 'Corrected', 'Suggestion')])
    correct = len([r for r in rows if r['status'] == 'Correct'])
    corrected = len([r for r in rows if r['status'] == 'Corrected'])
    suggestion = len([r for r in rows if r['status'] == 'Suggestion'])
    pct = round(reviewed / total * 100) if total else 0
    return {
        'total': total,
        'reviewed': reviewed,
        'correct': correct,
        'corrected': corrected,
        'suggestion': suggestion,
        'pct': pct
    }
