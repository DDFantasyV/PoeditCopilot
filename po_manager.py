import polib
import pickle


class POManager:
    def __init__(self):
        self.entries = []

    def clear(self):
        self.entries = []

    def load_new_mo(self, path):
        mo = polib.mofile(path)
        self.clear()
        for idx, entry in enumerate(mo):
            is_plural = bool(entry.msgid_plural)
            new_ru_text = entry.msgstr_plural.get(0, "") if is_plural else entry.msgstr
            self.entries.append({
                'entry_id': idx + 1, 'msgid': entry.msgid, 'is_plural': is_plural,
                'msgid_plural': entry.msgid_plural if is_plural else '',
                'new_ru_text': new_ru_text, 'old_ru_text': '', 'status': 'New',
                'translated_text': '', 'translated_plural': {}
            })
        return len(self.entries)

    def load_old_mo(self, path):
        old_mo = polib.mofile(path)
        old_map = {e.msgid: e for e in old_mo}
        new_ids = {item['msgid'] for item in self.entries}

        for item in self.entries:
            mid = item['msgid']
            if mid in old_map:
                old_entry = old_map[mid]
                item['old_ru_text'] = old_entry.msgstr_plural.get(0, "") if item['is_plural'] else old_entry.msgstr

                plural_changed = item['is_plural'] and (old_entry.msgid_plural != item['msgid_plural'])
                text_changed = (item['new_ru_text'] != item['old_ru_text'])

                item['status'] = 'Modified' if (text_changed or plural_changed) else 'Normal'
            else:
                item['status'] = 'New'

        for entry in old_mo:
            if entry.msgid not in new_ids:
                self.entries.append({
                    'entry_id': -1, 'msgid': entry.msgid, 'is_plural': bool(entry.msgid_plural),
                    'msgid_plural': entry.msgid_plural, 'new_ru_text': '', 'old_ru_text': entry.msgstr,
                    'status': 'Deleted', 'translated_text': '', 'translated_plural': {}
                })

    def load_translated_mo(self, path):
        cn_mo = polib.mofile(path)
        cn_map = {e.msgid: e for e in cn_mo}
        count = 0
        for item in self.entries:
            if item['msgid'] in cn_map:
                target_entry = cn_map[item['msgid']]
                if item['is_plural']:
                    if target_entry.msgstr_plural:
                        item['translated_plural'] = target_entry.msgstr_plural.copy()
                    elif target_entry.msgstr:
                        item['translated_plural'] = {0: target_entry.msgstr}
                else:
                    item['translated_text'] = target_entry.msgstr
                count += 1
        return count

    def export_mo(self, save_path, metadata_dict=None):
        new_po = polib.POFile(wrapwidth=0)
        if metadata_dict:
            new_po.metadata = metadata_dict
        else:
            new_po.metadata = {
                'Project-Id-Version': 'Mir Korabley',
                'Last-Translator': 'DDF_FantasyV',
                'Language-Team': '<REPAD Localization Team>',
                'Language': 'zh_SG',
                'Content-Type': 'text/plain; charset=UTF-8',
                'Content-Transfer-Encoding': '8bit',
                'Plural-Forms': 'nplurals=1; plural=0;'
            }
        count = 0
        for item in self.entries:
            if item['status'] == 'Deleted': continue
            if item['is_plural']:
                clean_plural_dict = {int(k): str(v) for k, v in item['translated_plural'].items()}
                entry = polib.POEntry(msgid=item['msgid'], msgid_plural=item['msgid_plural'],
                                      msgstr_plural=clean_plural_dict)
            else:
                entry = polib.POEntry(msgid=item['msgid'], msgstr=item['translated_text'])
            new_po.append(entry)
            count += 1

        new_po.save_as_mofile(save_path)
        new_po.save(save_path.replace('.mo', '.po'))
        return count

    def save_progress(self, path):
        with open(path, 'wb') as f:
            pickle.dump(self.entries, f)

    def load_progress(self, path):
        with open(path, 'rb') as f:
            self.entries = pickle.load(f)