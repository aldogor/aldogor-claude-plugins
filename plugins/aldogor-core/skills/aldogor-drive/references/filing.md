# Filing papers in Drive

This method is for folders of finished papers: documents that someone issues, cites or asks for as proof (contracts, certificates, invoices, payslips, tax returns, medical reports, identity cards). A live document, one whose next version is still to be made, follows the rule at the head of the skill instead: it lives where that next version is made.

## The unit and the names

- The unit is the single document: what is issued, cited or asked for as one thing. An act travels with what was signed together with it (a contract with its declarations). What an issuer sends in a single mailing stays together: letters follow the statement they arrive with, as the dates and subjects their pages share inside the PDF show. A payslip, an invoice, a purchase order, a certificate with its credit sheet and one year of an insurance policy are a file each. Series are split by period (one tax certificate per year and issuer, one bank statement per period as the bank issues it). A new document is added as a new file, and nothing is recomposed. An original keeps its content as it was downloaded.
- Inside a file the main act comes first and each page appears once, in the copy with the most signatures. Blank forms and generic instructions come out, except a blank form the user wants ready to print, which keeps a fixed title.
- Each folder has one function, and its structure and naming convention follow from it. One convention per folder, for files and sibling subfolders alike; a file that enters a folder takes its convention, and a file that cannot take it goes into a subfolder with its own.
- In folders of papers a name reads `YYYY-MM-issuer-what`, in the document's language, lowercase, words joined by hyphens. The month is the month of issue, or of the event for the papers of an event; an invoice or credit note carries its own number. Where documents of the same kind and issuer belong to different people, the second field is the person. A name uses the word the user searches by when the act's own word differs.
- A name comes from the text of the document, read first, never from the file's old title.
- Files that are regenerated (a CV, a cumulative register) keep a fixed title and are moved rather than renamed, so their links hold.
- A document kept both in Drive and in a repository is the same file on both sides, never a second version. The repository holds only what its work cites; names may differ but stay close.

## The order of work

When a whole Drive is to be reordered, the work starts from an inventory of the root, and each root folder gets one of four fates, which the user decides: reordered by this method (papers someone cites or asks for), settled as a block (one name and one place for the whole folder), handed to the project that owns it, or left as it is. A campaign of several sessions keeps its rules, the table of root folders and its journal in a repository of its own, which never holds the documents. When the campaign ends, the table and the rules move into a document named README at the root of the Drive, where the next reordering finds them.

A folder of papers is reordered in these steps.

1. Read-only inventory: name, type, size, date, owner and sharing of each file. With the Drive connector, a listing ordered by `modifiedTime desc` with `pageSize: 100` returns the whole folder; smaller pages repeat items.
2. First questions to the user, on the sections; the names are enough to decide them.
3. The user downloads the files to be read (the connector's download may be switched off). Files that are only moved, or renamed with a name already certain, stay in Drive.
4. Reading, page by page, from the text layer or OCR. Personal data (tax codes, bank details, document numbers, amounts, health data) is not copied into the chat, the journal or the table; a document is described by its kind, issuer and date. A page that appears to carry a password or PIN is not transcribed. It is extracted into a file of its own for the user to look at, and named by file and page in the list of what is left to the user.
5. Second questions: what to split, which copy of a pair to keep, which date names an identity document (issue or expiry), what is not worth keeping.
6. One table of renames, moves, splits and removals, each with its action, destination and reason in one line, which the user approves.
7. Application, one block at a time, each with the user's go-ahead in words: folders, then renames and moves of whole files, then uploads, then shared folders, then removals. Before each block the folder is listed again, so that ids come from Drive and not from the inventory.
8. The project's journal and table, and a step-by-step list of what is left to the user (files above the connector's upload limit to drag by hand, the removal folder to empty).

## Cautions

- Moves and removed pages go by explicit lists, file by file and page by page. A rule such as "everything except" takes a stranger file, and an automatic blank-page detector drops pale printed sheets.
- For every source, each page ends in exactly one file or in a list of excluded pages with the reason. Pages are copied without recompression, and the first and last page of each new file are looked at.
- Splitting a file is the one operation that cannot be redone. The source files stay until a session other than the one that cut them has rechecked the cuts against the sources, image against image.
- Removal goes through a folder named for deletion, which the user empties; never the bin.
- Medical image sets (DICOM) and their archives stay as received, one unit per examination: not opened, converted or recompressed. Of a spreadsheet, the sheet names and headers are read.
- A shared file or folder is reported before any proposal touches it: a move changes the access a file inherits from its folder, and for a folder others write in, each proposal says what changes for them. Colleagues' files follow the rule on renames in the skill.
- When two readings of a request lead to different work, ask.
- A boundary between two documents inside one scan is set only after reading the page before it and the page after it.
- A cut page is compared with its source by image: a text comparison does not see a signature or a stamp.
- A difference between a cut and its source is looked at with the before and after side by side before it is called harmless.
- On papers with sensitive content (health, money, identity), a tool prints only dates and words from a closed list, since a line picked by keyword can carry the data itself. A whole line of a paper with amounts is printed only through maskings that have been tested and that cover the thousands separator: a masking written on the spot misses the separator, and the thousands digit of an amount passes.

## Tool limits

These come from practice and change with the tools; the maintenance of the setup rechecks them.

- Splitting a PDF turns its form fields (electronic signatures, dates, buttons) into drawing: the new file shows them but no longer holds them as fields.
- The Drive connector uploads only files inside the session's working folder, by reference, up to about 7 MB; larger files are dragged by hand, and a PDF stays a PDF only with the option that disables conversion.
- Permissions read through the connector do not tell access given directly from access inherited from a folder.
- Reading a file's text through the Drive connector returns only the pages that have a text layer.
- The Drive connector also moves and renames files and folders that other people own, inside the folders where the user can edit, so nothing on the connector's side stops a change to a colleague's file.
