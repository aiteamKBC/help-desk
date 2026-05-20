# Knowledge Base Builder Feature Documentation

## Project Overview

Knowledge Base Builder is a lightweight internal web app for creating, saving, searching, opening, editing, and archiving support knowledge base articles.

The app is built as a static browser interface with an optional local Node.js server. When opened through the server, articles are saved directly into the project folders. When opened as a plain local HTML file, articles can still be created and downloaded manually.

## Main User Areas

### Article Creation

The Article Creation view is the main editor for building support articles.

It includes:

- Article title field
- Keywords field
- Four structured article sections:
  - Inquiry
  - Summary
  - Steps
  - Resources
- Section-specific attachments
- Save article action
- Clear form action
- Import article for editing

This structure keeps every article consistent and searchable.

### Knowledge Center

The Knowledge Center view is the searchable article library.

Users can:

- Search indexed articles
- Open an article preview
- Edit an existing article
- Remove an article from the active library
- See article count
- See article file names and created/edited dates where available

Search checks article title, keywords, file name, inquiry, summary, steps, and resources.

## Feature Details

### 1. Structured Article Builder

Each article is built from a consistent schema:

- `title`
- `keywords`
- `sections.inquiry`
- `sections.summary`
- `sections.steps`
- `sections.resources`
- `attachments`
- `createdAt`
- `updatedAt`

The schema is embedded inside exported article HTML using a hidden template element. This allows saved articles to be reopened and edited later.

### 2. Article Saving

When the app is running through the local server with:

```bash
npm start
```

the Save article button writes the generated HTML article into:

```text
Articles/
```

Attached files are written into:

```text
Evidence/
```

If the app is opened directly as `index.html`, browser security prevents direct folder writes. In that case, the app downloads the generated HTML article instead.

### 3. Article Filename Generation

New article file names are generated from the article title.

Example:

```text
Reset Microsoft Authenticator
```

becomes:

```text
reset-microsoft-authenticator.html
```

If a filename already exists in the Knowledge Center index, the app appends a number, such as:

```text
reset-microsoft-authenticator-2.html
```

When editing an existing article, the app keeps the existing filename.

### 4. Attachments and Evidence

Each article section has its own attachment area.

Supported attachment actions:

- Add files using a file picker
- Drag files into a section
- Paste screenshots into a section
- Add links
- Open attachments
- Download embedded attachment data before saving
- Remove attachments from a draft

When saved through the server, uploaded files are stored in the `Evidence/` folder and referenced by article HTML.

Image attachments are displayed inside the exported article in an expandable image preview.

### 5. Import for Editing

Users can import an existing article file from the sidebar.

Supported import formats:

- `.html`
- `.htm`
- `.json`

For HTML imports, the app looks for embedded article JSON in the exported article. If the HTML was created by this builder, the article can be restored into the editor with its title, keywords, sections, dates, and attachments.

### 6. Article Search

The Knowledge Center search is keyword based.

Search terms are matched against:

- Article title
- Keywords
- File name
- Inquiry
- Summary
- Steps
- Resources

When multiple words are entered, every word must exist somewhere in the article search text.

### 7. Opening Articles

The Open action displays a generated static article preview in a new browser tab.

The preview includes:

- Article title
- Keywords
- Created date
- Edited date, if available
- Inquiry
- Summary
- Steps
- Resources
- Attachments
- Clickable links in article text

### 8. Editing Existing Articles

The Edit action loads an indexed article back into the Article Creation form.

If the article has embedded JSON data, the full editable article is restored. If only partial index metadata is available, the app loads the available fields and warns the user that the original article file may be needed for full attachment data.

### 9. Removing Articles

When running through the local server, removing an article from the Knowledge Center moves the saved article file into:

```text
Articles/Bin/
```

This keeps removed articles recoverable instead of permanently deleting them.

If the app is opened directly as a file, the remove action only removes the article from the browser's local Knowledge Center index.

### 10. Browser Local Storage

The app uses browser local storage for:

- Draft article data
- Knowledge Center index data

Storage keys used by the current app version:

```text
kb_article_builder_v10
kb_article_index_v10
```

If the index becomes too large for browser storage, search still works for the current session, but the app shows a warning.

### 11. Default Articles

The app loads bundled default article metadata from:

```text
src/default-articles.js
```

The current bundled default article is:

```text
Gateway Digital Signature
```

When running through the server, the app also reads saved articles directly from the `Articles/` folder.

### 12. Local Server API

The local Node server is defined in:

```text
server.mjs
```

It serves the app and provides article file operations.

#### GET `/api/articles`

Returns indexed article metadata from the `Articles/` folder.

The server reads `.html`, `.htm`, and `.json` files and attempts to extract article metadata.

#### POST `/api/articles`

Saves an article into the `Articles/` folder.

Request body includes:

- `filename`
- `html`
- `evidence`

Evidence items are decoded from data URLs and saved into `Evidence/`.

#### DELETE `/api/articles`

Moves an article from `Articles/` into `Articles/Bin/`.

The server only allows valid `.html`, `.htm`, or `.json` article filenames.

## Project File Structure

```text
Knowledge_Base_Builder/
|-- index.html
|-- package.json
|-- server.mjs
|-- src/
|   |-- app.js
|   |-- default-articles.js
|   `-- styles.css
|-- Articles/
|   |-- Bin/
|   |-- gateway-digital-signature.html
|   |-- KSBs.html
|   |-- lms-cannot-reset-password.html
|   `-- teams-presenter-access.html
`-- Evidence/
    |-- gateway-digital-signature.JPG
    |-- LMS_reset_1.JPG
    |-- LMS_reset_2.JPG
    |-- LMS_reset_3.JPG
    |-- Marketing_Executive_KSBs_1.JPG
    |-- Marketing_Executive_KSBs_2.JPG
    `-- Where_KSBs.JPG
```

## Running the Project

Install dependencies if needed, then start the server:

```bash
npm start
```

The server runs on:

```text
http://localhost:4173
```

The port can be changed with the `PORT` environment variable.

## User Workflow

### Create a New Article

1. Open the Article Creation tab.
2. Select New article.
3. Enter title and keywords.
4. Complete the Inquiry, Summary, Steps, and Resources sections.
5. Add evidence files, screenshots, or links where needed.
6. Select Save article.

### Find an Existing Article

1. Open the Knowledge Base tab.
2. Enter a keyword, title, system name, or issue description.
3. Review matching results.
4. Select Open to view the article or Edit to update it.

### Update an Existing Article

1. Open the Knowledge Base tab.
2. Search for the article.
3. Select Edit.
4. Make changes in the Article Creation form.
5. Select Save article.

### Archive an Article

1. Open the Knowledge Base tab.
2. Search for the article.
3. Select Remove.
4. When running through the server, the article is moved to `Articles/Bin/`.

## Data and Safety Notes

- The server sanitizes filenames before writing files.
- Static file serving blocks direct access to `Articles/Bin/`.
- Article deletion is implemented as a move to `Articles/Bin/`, not permanent deletion.
- Attachments saved through the server are stored separately from article HTML in `Evidence/`.
- Exported article HTML contains structured JSON so the article can be edited again later.

## Current Limitations

- There is no login or user permission system.
- Article changes are saved immediately to local project files when using the server.
- Search is simple keyword matching, not semantic search.
- Attachments are referenced by filename, so duplicate evidence filenames can overwrite earlier files.
- The browser local index may become too large if many large article records are stored.
- There is no built-in restore button for files moved to `Articles/Bin/`.

## Future Enhancement Ideas

- Add confirmation prompts before removing articles.
- Add restore from `Articles/Bin/`.
- Add article categories or tags.
- Add richer version history.
- Add duplicate evidence filename handling.
- Add export/import of the full knowledge base.
- Add advanced filters for date, keyword, and article source.
- Add authentication if deployed beyond a trusted local environment.
