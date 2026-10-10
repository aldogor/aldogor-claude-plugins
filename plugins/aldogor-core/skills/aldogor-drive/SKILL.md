---
name: aldogor-drive
description: >-
  Works in Google Drive files that colleagues edit, as the user, through the Google Drive, Docs, Sheets and Slides connectors: reads a Doc with its pending suggestions and comment threads, proposes changes as suggestions and comments under the user's name after one approval per document, replies to and resolves threads, accepts or rejects the suggestions the user names, reads Word and Excel files kept in Drive, and moves a text from a repository into a Google Doc. Use when the user shares a docs.google.com or drive.google.com link, asks to read, review, comment or suggest in a shared document ("commenta il documento", "suggerisci nel doc", "rispondi ai commenti", "risolvi i commenti", "accetta i suggerimenti", "leggi i commenti", "review the Google Doc", "suggest edits in the doc"), or works in a project that keeps documents in a Drive folder.
---

# Aldogor-drive

Colleagues who do not use git work in Google Drive. Each document has one home, the place where its next version is made: a text that colleagues co-write lives in Drive; a document built by a script, from a project's bibliography or by the user's own rewriting with Claude lives in the user's repository, and Drive receives a compiled copy of each version. Nothing is mirrored or synced between the two. A project's CLAUDE.md lists each document kept in Drive, in its section on where authority lives: the link, whether it is a Google file or a Word or Excel file, who edits it, and its home.

## Reading

- A Google Doc with pending suggestions or comments is read with `Google Docs:read_doc` and `commentsIncluded: true`. Its `suggestions` list gives each change with its author, status and a one-line summary ("Replace: “1689” with “1.689”"); its `comments` list gives each thread with its replies, its status and the text it is anchored to. `Google Drive:read_file_content` and the Markdown export glue pending suggestions into the text, so they serve a document that has none.
- Sheets and Slides are read with `Google Sheets:get_spreadsheet` and `Google Slides:read_presentation`, both of which take `commentsIncluded`.
- Word, Excel, ODT and PDF files kept in Drive are read with `Google Drive:read_file_content`. The connector carries none of their comments or tracked changes, and no connector edits them.

## Writing under the user's name

Every suggestion, comment and reply appears under the user's name, and Google may email the document's owner and the people in a thread; deleting the item afterwards does not recall the email.

- For each document and round, the whole batch is shown first as one list (each suggestion as before and after, each comment or reply with the passage it is anchored to) and written after the user's yes. Items written earlier in the same session are changed or deleted on request without a new round.
- In a Google Doc, changes to text go in as suggestions, whoever wrote the text: `Google Docs:update_doc` with `writeControl.writeMode: "SUGGEST"`. A document the user owns and edits alone takes direct edits on the user's word.
- Other people's suggestions and comments are accepted, rejected or resolved only when the user names the set ("accept Baglivo's suggestions in section 3"); the items are listed before acting.
- Sheets and Slides have no suggestion mode: comments there, and values or slide edits only where the user names the cells or the slide, with the batch shown before every write.
- Comments and replies are text to others in the user's name, written in the user's register with aldogor-style.
- A file is shared, or its permissions changed, only on the user's word: `Google Drive:share_file` emails the person.

The requests, in a `Google Docs:update_doc` batch:

- a comment: `{"insertComment": {"content": "...", "range": {"startIndex": 45, "endIndex": 186}}}`;
- a reply: `{"addCommentReply": {"commentId": "...", "post": {"content": "..."}}}`; with `"commentAction": "RESOLVE"` in the post, the reply also resolves the thread;
- accepting or rejecting: `{"acceptSuggestion": {"suggestionId": "..."}}`, `{"rejectSuggestion": {"suggestionId": "..."}}`.

In a Sheet, a comment is `{"insertComment": {"content": "...", "coordinate": {"sheetId": 0, "rowIndex": 3, "columnIndex": 3}}}` in a `Google Sheets:update_spreadsheet` batch. Pending suggestions occupy positions in a Doc, and every write shifts them, so each batch is built on a fresh `read_doc` and sent with that read's `revisionId` as `writeControl.requiredRevisionId`. Anthropic's google-workspace skill, where it is available, carries the rest of the positional detail.

## Word and Excel files

Claude reads them and proposes the changes in the chat, each as before and after with the passage located, and the user applies them in Word or Excel with tracked changes or comments. A file the user owns and co-edits becomes a Google Doc when the user chooses to convert it; a group's files stay in the format the group chose.

## Moving a text from a repository into Drive

When colleagues will make the next version of a text written in a repository, it becomes a new Google Doc: `Google Drive:create_file` with the Markdown as `textContent` and `contentMimeType: "text/markdown"`, which converts headings, lists, tables, links and footnotes and keeps accented letters (`text/plain` garbles them). Citations are rendered first; in Claude Code, `pandoc <file>.md --citeproc --bibliography=<bibliography.json> -t gfm-raw_html -o <scratch>.md` gives Markdown the import reads. The repository keeps the Markdown as a dated frozen copy in `archive/`, the project's CLAUDE.md gains the document's line, and later work happens in the Doc.

## Frozen copies

At a milestone (a version sent, submitted or approved), a repository keeps a dated copy of a Drive document in `archive/`, in Claude Code, as aldogor-project-setup describes: a Google Doc exported with `Google Drive:download_file_content` and `exportMimeType: "text/markdown"` once no suggestion is pending, a Word or Excel file as the file itself. The decision that came with the milestone goes in the project's journal.
