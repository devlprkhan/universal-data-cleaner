# How the OpenCode docs site authors and builds its pages

Evidence base: every file referenced below was downloaded from
`anomalyco/opencode@dev` and saved under `docs/reference/src/` (flattened names, original path
recoverable from the name). URLs came from
`https://raw.githubusercontent.com/anomalyco/opencode/dev/services/site/<path>` and directory
listings from `https://api.github.com/repos/anomalyco/opencode/contents/<dir>?ref=dev`.

Saved evidence (46 files) — `docs/reference/src/`:

| Saved file | Original path |
| --- | --- |
| `docs-AGENTS.md` | `services/site/src/docs/AGENTS.md` |
| `docs-config.ts` | `services/site/src/docs/config.ts` |
| `docs-content.ts` | `services/site/src/docs/content.ts` |
| `docs-frontmatter.ts` | `services/site/src/docs/frontmatter.ts` |
| `docs-route.ts` | `services/site/src/docs/route.ts` |
| `docs-render.tsx` | `services/site/src/docs/render.tsx` |
| `docs-document.tsx` | `services/site/src/docs/document.tsx` |
| `docs-vite.ts` | `services/site/src/docs/vite.ts` |
| `docs-middleware.ts` | `services/site/src/docs/middleware.ts` |
| `docs-client.ts` | `services/site/src/docs/client.ts` |
| `docs-modules.d.ts` | `services/site/src/docs/modules.d.ts` |
| `docs-recma-solid.ts` | `services/site/src/docs/recma-solid.ts` |
| `docs-remark-links.ts` | `services/site/src/docs/remark-links.ts` |
| `docs-remark-slots.ts` | `services/site/src/docs/remark-slots.ts` |
| `docs-remark-starlight.ts` | `services/site/src/docs/remark-starlight.ts` |
| `docs-rehype-headings.ts` | `services/site/src/docs/rehype-headings.ts` |
| `docs-rehype-table-scroll.ts` | `services/site/src/docs/rehype-table-scroll.ts` |
| `docs-rehype-shiki.ts` | `services/site/src/docs/rehype-shiki.ts` |
| `docs-lib-navigation.ts` | `services/site/src/docs/lib/navigation.ts` |
| `docs-lib-llms.ts` | `services/site/src/docs/lib/llms.ts` |
| `docs-lib-openapi.ts` | `services/site/src/docs/lib/openapi.ts` |
| `docs-lib-sitemap.ts` | `services/site/src/docs/lib/sitemap.ts` |
| `docs-lib-v1-navigation.ts` | `services/site/src/docs/lib/v1-navigation.ts` |
| `docs-layouts-DocsLayout.tsx` | `services/site/src/docs/layouts/DocsLayout.tsx` |
| `docs-components-Callout.tsx` | `services/site/src/docs/components/Callout.tsx` |
| `docs-components-Card.tsx` | `services/site/src/docs/components/Card.tsx` |
| `docs-components-CardGroup.tsx` | `services/site/src/docs/components/CardGroup.tsx` |
| `docs-components-CodeBlock.tsx` | `services/site/src/docs/components/CodeBlock.tsx` |
| `docs-components-CodeTabs.tsx` | `services/site/src/docs/components/CodeTabs.tsx` |
| `docs-components-DocsFooter.tsx` | `services/site/src/docs/components/DocsFooter.tsx` |
| `docs-components-DocsSearchDialog.tsx` | `services/site/src/docs/components/DocsSearchDialog.tsx` |
| `docs-components-DocsSidebar.tsx` | `services/site/src/docs/components/DocsSidebar.tsx` |
| `docs-components-OpenApiReference.tsx` | `services/site/src/docs/components/OpenApiReference.tsx` |
| `docs-components-PlanTabs.tsx` | `services/site/src/docs/components/PlanTabs.tsx` |
| `docs-components-Slot.tsx` | `services/site/src/docs/components/Slot.tsx` |
| `docs-components-Tabs.tsx` | `services/site/src/docs/components/Tabs.tsx` |
| `docs-script-build.ts` | `services/site/src/docs/script/build.ts` |
| `docs-script-validate-links.ts` | `services/site/src/docs/script/validate-links.ts` |
| `docs-components-_listing.json` | directory listing of `src/docs/components/` (trimmed) |
| `docs-content-_listing.json` | directory listing of `src/docs/content/` (trimmed) |
| `docs-content-build-_listing.json` | directory listing of `src/docs/content/build/` (trimmed) |
| `docs-content-cli-_listing.json` | directory listing of `src/docs/content/cli/` (trimmed) |
| `docs-content-console-_listing.json` | directory listing of `src/docs/content/console/` (trimmed) |
| `docs-content-index.mdx` | `src/docs/content/index.mdx` (verbatim) |
| `docs-content-config.mdx` | `src/docs/content/config.mdx` (verbatim) |
| `docs-content-mcp-servers.mdx` | `src/docs/content/mcp-servers.mdx` (verbatim) |

The four `*_listing.json` files preserve every entry name/path/type/size from the GitHub contents
API; only the API's `url`/`_links`/`sha` plumbing was dropped for readability (the file says so in
its `_note`). Everything else is verbatim.

---

## 1. Content format

### File extensions and layout

- **Extension: `.mdx` only.** `vite.ts` globs `./**/*.mdx` for each set's folder, and
  `script/build.ts`/`slugsOf()` only counts `.mdx` files. There is no `.md` source file anywhere;
  the `.md` files at build output are *generated* (the "Markdown twins").
- **URL path == file path.** From `AGENTS.md`: "Content lives in `content/` as MDX. A file's path is
  its URL: `content/cli/keybinds.mdx` is `/docs/cli/keybinds/`. Other repositories read some of these
  files by path, so don't move them without checking."
- Layout under `services/site/src/docs/content/` (from `docs-content-_listing.json`): 29 top-level
  entries — 25 flat `.mdx` pages plus 4 directories (`build/`, `cli/`, `console/` and, inside
  `build/`, `client/`, `plugins/`, `sdk/`; inside `console/`, `api/`, `harnesses/`). A directory's
  landing page is its `index.mdx` (`content/build/index.mdx` → `/docs/build/`).
- There is a second docs set, V1, at `services/site/src/docs/v1/content` (18 locales), mounted at
  `/v1/docs/` and `noindex: true`. Its MDX is the old Starlight app's syntax (see §3.7).

### Frontmatter keys actually used

`frontmatter.ts` is the whole schema (zod). The keys a page may use:

| Key | Type | Required | Meaning | Real example |
| --- | --- | --- | --- | --- |
| `title` | `string` | **yes** | Page title. Becomes `<h1>`, `<title>` (`"{title} \| OpenCode"`), the search-result title and the sidebar-agnostic page name. Content bodies start at `##`; the `# H1` is *not* in the markdown. | `title: "MCP servers"` (`docs-content-mcp-servers.mdx`) |
| `description` | `string` | no | `<meta name="description">` and OG metadata. Default when absent: `` `${title} documentation for OpenCode.` `` | `description: "Connect OpenCode to local and remote Model Context Protocol servers with opencode mcp add or in config, including OAuth sign-in."` |
| `noindex` | `boolean` | no | Adds `<meta name="robots" content="noindex">` and drops the `data-pagefind-body` attribute (page kept out of search). | `noindex: true` (schema default set only if written) |
| `tableOfContents` | `boolean`, or `{ minHeadingLevel?: 1-6, maxHeadingLevel?: 1-6 }` | no | `false` empties the Contents rail. `document.tsx`: `headings={module.frontmatter.tableOfContents === false ? [] : module.headings}`. | `tableOfContents: false` |

Notes on frontmatter handling:

- Parsing is done in `vite.ts` `compileMdx()` with a hand-rolled regex
  `/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/` and `yaml.parse`, then `frontmatterSchema.safeParse`.
  Failure throws `` `${id}: invalid frontmatter\n${parsed.error.message}` ``. Only `title` is
  mandatory. The block is replaced with blank lines so MDX error line numbers stay correct.
- The parsed object is serialised verbatim into the module (`export const frontmatter = …`), so the
  three-page `tableOfContents` object form flows straight to `DocsLayout`.
- Not found: no `sidebar`, `weight`, `order`, `slug`, `editUrl`, `icon`, `status`, `draft`, or
  `redirect` key exists in the content or the schema. Ordering is **not** frontmatter-driven.

### Ordering / nav grouping

**An explicit TypeScript array is the single source of truth — not directory order, not sidebar meta
files.** From `AGENTS.md`: "`lib/navigation.ts` is the source of truth for header sections and
sidebar ordering."

`docs-lib-navigation.ts` exports `docsSections: DocsSection[]`, five sections in display order:

```ts
export interface DocsSection {
  key: "docs" | "cli" | "build" | "api" | "console"
  title: string                       // e.g. "Docs", "CLI", "Build", "API", "Console"
  landingSlug: string                 // e.g. "index", "cli", "build", "api", "console"
  groups: DocsNavGroup[]              // sidebar groups, in order
}
export interface DocsNavGroup { title?: string; items: DocsNavItem[] }
export interface DocsNavItem { title: string; slug: string; href?: string }
```

Concrete excerpt:

```ts
{ key: "docs", title: "Docs", landingSlug: "index",
  groups: [
    { items: [                       // untitled first group
      { title: "Intro", slug: "index" },
      { title: "Config", slug: "config" },
      { title: "Migrate from V1", slug: "migrate-v1" },
      { title: "Enterprise", slug: "enterprise" },
      { title: "Troubleshooting", slug: "troubleshooting" }] },
    { title: "Configure", items: [ { title: "Agents", slug: "agents" }, /* …*/ ] }] }
```

Consequences a reimplementation must copy:

- This list drives the sidebar order **and** the previous/next pagination (`DocsLayout` flattens
  `section.groups` and finds the current slug) **and** the order of `llms.txt` and `sitemap.xml` (both
  iterate `docsSections`).
- A group whose `title` equals the section's `title` renders without a group heading
  (`DocsNav`: `group.title === props.section ? undefined : group.title`). This is why the API group
  titled `"API"` has no visible group label.
- `getDocsSection(slug)` scans the sections and **falls back to `docsSections[0]`** when the slug is
  not listed — so a page that exists as a file but is missing from `navigation.ts` still renders,
  under the Docs sidebar.
- `href?: string` marks an item that lives in another set (the V1 sidebar reuses Console pages). Such
  items are excluded from pagination and from `llms.txt`.

### Slug and URL derivation

`docs-lib-navigation.ts` holds the three functions:

```ts
/** A content file's slug: its path under content/ without `.mdx` or a trailing `/index`. */
export function docsSlug(file: string) {
  const slug = file.replace(/\.mdx$/, "")
  return slug === "index" ? slug : slug.replace(/\/index$/, "")
}

const assetSlugs = new Set(["api"])   // pages whose URL has no trailing slash

export function docsHref(slug: string, set: DocsSet) {
  const path = slug === "index" ? "" : `${slug.replace(/\/index$/, "")}${assetSlugs.has(slug) ? "" : "/"}`
  return `${set.base}${path}`
}

export function docsMarkdownHref(slug: string, set: DocsSet) {
  return slug === "index" ? `${set.base}index.md` : `${docsHref(slug, set).replace(/\/$/, "")}.md`
}
```

| Source file | Slug | URL |
| --- | --- | --- |
| `content/index.mdx` | `index` | `/docs/` |
| `content/config.mdx` | `config` | `/docs/config/` |
| `content/cli/index.mdx` | `cli` | `/docs/cli/` |
| `content/cli/keybinds.mdx` | `cli/keybinds` | `/docs/cli/keybinds/` |
| *(no file; generated)* | `api` | `/docs/api` (no trailing slash) |

To this, `route.ts` adds: a `.md` suffix on a page URL returns the Markdown twin, and
`/docs.md` is rewritten to `/docs/index.md`; requesting a page with a trailing slash when the
canonical form has none issues a **307** to the canonical URL.

### Redirects / aliases

There is no per-page alias syntax. Redirects are three hard-coded mechanisms:

1. **`moved` map in `route.ts`** (a lower-cased slug → new slug map, answered with **301**):
   `console/inference→console/api/inference`, `go→console/go`, `zen→console/models`,
   `rules→instructions`, `sdk→build/sdk`, `server→api`, `keybinds→cli/keybinds`, `tui→cli/tui`,
   `web→cli/web`, `acp→cli/acp`, `modes→agents`, `custom-tools→build/plugins/server`.
2. **Unclaimed `/docs/...` paths → the same path under `/v1/docs`** with **302** (temporary, because
   V2 may add the page later). Comment: "adding a page here takes its URL over."
3. **Host redirect**: any `docs.*` hostname is redirected **301** to the same path under `/docs` on
   the bare host (`docsHostRedirect`). Per `AGENTS.md`, the old `/v2` URLs redirect to `/docs`
   permanently via `src/lib/legacy.ts` — *that file was not downloaded* ("not found" locally).
   V1 also has language-alias redirects (its own middleware's names: `en/root/uk→""`, `zh→zh-cn`,
   `zht→zh-tw`, `br/pt→pt-br`, `no/nn→nb`) and schema redirects (`config.json`/`tui.json` → `/{name}`).

---

## 2. Markdown features in use

The MDX compile options (`vite.ts`):

```ts
const compiled = await compile(file, {
  jsx: true, format: "mdx",
  elementAttributeNameCase: "html", stylePropertyNameCase: "css",
  remarkPlugins: set.id === "v1" ? v1Plugins(id)
    : [remarkGfm, remarkSmartypants, [remarkDocsLinks, { base: set.base }], remarkSlots],
  rehypePlugins: [rehypeShiki, rehypeTableScroll, rehypeHeadings],
  recmaPlugins: [recmaSolid],
})
```

So the enabled syntax is **GitHub-Flavoured Markdown + smart punctuation + MDX JSX**, and that is all.

| Feature | Present? | How it appears in the real content |
| --- | --- | --- |
| GFM tables | yes | `docs-content-mcp-servers.mdx` has many, e.g. `\| Field \| Required \| Description \|` followed by `\| --- \| --- \| --- \|`. |
| GFM autolinks / strikethrough / task lists | available (remark-gfm); the three sampled files show plain links only | — |
| Smart punctuation | yes (`remark-smartypants`) | Sources contain straight quotes that typographic output converts; the sampled files show a real curly apostrophe: `It’s available as a terminal-based interface`. |
| Fenced code | yes, heavily | ```` ```sh ````, ```` ```jsonc ````, ```` ```json ````, ```` ```text ````, ```` ```bash ````. |
| Fence **title** meta | yes | ```` ```jsonc title="opencode.jsonc" ```` and ```` ```json title="opencode.json" ````. |
| Shell sessions with prompts | yes | `docs-content-index.mdx`: ```` ```bash ```` block whose body is `$ opencode pair` then indented output. |
| File-tree fences | yes | ```` ```text ```` blocks whose body contains `├──` / `└──` (see `docs-content-config.mdx`, `/etc/opencode/` tree). |
| Diff fences | supported by the highlighter | `lang === "diff"` branch in `rehype-shiki.ts`; no `diff` fence in the three sampled files. |
| Admonitions / callouts | **not `:::` in V2** | V2 uses the MDX component: `<Callout type="warning">…</Callout>` (`docs-content-config.mdx`, Experimental section). The `:::tip[Title]` directive syntax exists **only in the V1 set** (Starlight), handled by `remark-directive` + `remark-starlight.ts`. |
| Tabs | **not `===`** | Tabs are components: `<CodeTabs id=… label=… tabs={[{label, code}]} />` (V2, `docs-content-index.mdx`) and `<Tabs>` / `<PlanTabs>` (V1 / plan panels). |
| `<Component>` inside markdown (MDX) | yes | `<CodeTabs …/>`, `<Callout type="warning">` in the sampled files; `<Card>`, `<CardGroup>`, `<CodeBlock>`, `<PlanTabs>`, `<Tabs>`, `<Slot>` registered in `document.tsx`. |
| Raw HTML in markdown | yes | `<div class="docs-table-scroll">` is explicitly supported (comment in `rehype-table-scroll.ts`: "Some pages already wrap tables by hand in an MDX `<div class="docs-table-scroll">`"). |
| Named slots | yes | `<div slot="go">…</div>` inside a component becomes `<Slot name="go">…</Slot>` (see §3.6). |
| Cards / grids | yes | `<Card title href>` + `<CardGroup cols?>` components; not in the three sampled files but registered and documented in `AGENTS.md`. |
| Steps | V1 only | `<Steps>` is unwrapped by `remark-starlight.ts` into a `data-component="steps"` list. |
| API blocks | special-cased | The `/docs/api` page is **not** markdown at all; `OpenApiReference.tsx` renders `packages/protocol/openapi.json` (not downloaded; outside `src/docs/`). Markdown twins are skipped for `api` (`route.ts`: "The API reference has no Markdown twin"). |
| Explicit heading anchors `## Foo {#anchor}` | **not found** | Heading ids are generated from heading text by `github-slugger`; the only way to force an id is an explicit MDX `<h2 id="…">` element (as the API page does). No `{#…}` attribute syntax appears in any downloaded file. |
| Attribute syntax `{.class}` | **not found** | — |

---

## 3. The custom remark / rehype plugins

Order matters: remark runs first (`remarkGfm → remarkSmartypants → remarkDocsLinks → remarkSlots`),
then rehype (`rehypeShiki → rehypeTableScroll → rehypeHeadings`), then recma (`recmaSolid`).

### 3.1 `remark-links.ts` — docs-root-relative links

Adds the set's base to every markdown link whose URL starts with `/`. Only `link` nodes; images are
left alone.

```ts
if (node.type === "link" && node.url?.startsWith("/")) node.url = `${docsBase}${node.url}`
// docsBase = options.base.replace(/\/$/, "")
```

- Before: `[Config](/config)` → After: `<a href="/docs/config">`. The raw source keeps `/config`.
- `AGENTS.md` rule: "Keep internal Markdown links docs-root-relative, for example `/config`;
  `remark-links.ts` adds `/docs`."
- External and already-prefixed URLs are untouched (only a leading `/` triggers it).

### 3.2 `remark-slots.ts` — Astro-style named slots

For every JSX node whose component name starts with an uppercase letter, each JSX child carrying a
string `slot="…"` attribute is rewritten:

```ts
return { ...child, name: "Slot",
  attributes: [{ type: "mdxJsxAttribute", name: "name", value: slot.value }],
  children: [{ ...child, attributes: child.attributes.filter((a) => a !== slot) }] }
```

- Before:
  `<PlanTabs id=… label=… syncKey=…>\n  <div slot="go">Go panel</div>\n  <div slot="go-plus">…</div>\n</PlanTabs>`
- After: children become `<Slot name="go"><div>Go panel</div></Slot>`, etc.
- `components/Slot.tsx` consumes it: `SlotScope` provides a name, `Slot` renders its children only
  when there is no scope or the names match (`<Show when={scope === undefined || scope === props.name}>`).
  So outside any scope a slot always shows, and inside a scope only the matching slot shows.

### 3.3 `rehype-headings.ts` — heading ids + Contents data + `HeadingLink`

Runs over the HAST for every page:

- Assigns a GitHub-style id to **every** `h1`–`h6` that does not already have one, using
  `github-slugger` on the heading's text (text is gathered from `text`, `raw` and
  `mdxTextExpression` nodes, so inline MDX expressions are included literally).
- Records `{ depth, slug, text }` for every heading into `file.data.headings` — this is what becomes
  the page module's `headings` export and the Contents rail.
- Wraps the inner content of **h2 and h3 only** in the site's `HeadingLink` component so a click can
  copy the section URL:

  ```ts
  const link = { type: "mdxJsxTextElement", name: "HeadingLink",
    attributes: [{ name: "id", value: slug }, { name: "title", value: text }],
    children: node.children }
  node.children = [link]
  return "skip"
  ```

- Before: `## Setup` → After (conceptually)
  `<h2 id="setup"><HeadingLink id="setup" title="Setup">Setup</HeadingLink></h2>`,
  and `headings` gains `{ depth: 2, slug: "setup", text: "Setup" }`.
- `DocsLayout` then keeps only `depth === 2 || depth === 3` for the Contents rail, preserving the
  `level` for `data-level="3"` indentation.

### 3.4 `rehype-table-scroll.ts` — responsive table wrapper

Wraps every `<table>` element in `<div class="docs-table-scroll" tabindex="0">`, skipping any
subtree that already has that class (so hand-wrapped tables are not double-wrapped):

```ts
child.tagName === "table" ? {
  type: "element", tagName: "div",
  properties: { className: ["docs-table-scroll"], tabIndex: 0 },
  children: [child],
} : child
```

- Before: `<table>…</table>`
- After: `<div class="docs-table-scroll" tabindex="0"><table>…</table></div>`
- Rationale (source comment): "Wide Markdown tables would otherwise widen the whole page on small
  screens." `isScroller` recognises both HAST `className` arrays and raw `class`/`className`
  attributes written in MDX.

### 3.5 `rehype-shiki.ts` — fenced code → the site's `CodeFrame`

Finds every `pre` that contains exactly one `code` element (skipping `language-math`), takes the
language from the `language-*` class, the `title="…"` from the fence meta, and the text, then
replaces the block with an MDX `CodeFrame` (and sometimes `FileTree`) node. Rules, in order:

1. **File tree** — a `text`/`txt`/`plaintext` fence **with no title** whose body matches `[├└]──`:
   `CodeFrame variant="fileTree" kind="tree"` wrapping `FileTree tree={text}`. The `tree` string is
   parsed by the site's `FileTree`.
2. **Shell** — languages `bash, sh, shell, zsh, console`: `CodeFrame variant="terminal"
   kind="terminal"`. If any line starts with `"$ "`, the block is rendered as a terminal session:
   each `$ ` line becomes `<span data-token="prompt">$ <highlighted command></span>`, every other
   line `<span data-token="output">…</span>`, and **Copy contains only the commands**
   (`lines.filter(l => l.startsWith("$ ")).join("\n")`).
3. **Diff** — `lang === "diff"`: `CodeFrame variant="codeDiff"`, output
   `<pre data-component="code-diff" tabindex="0" data-funnel-copy="snippet" data-funnel-method="diff">`
   with one `<code data-diff="+"|"-"|" ">` row per line; each row is
   `<span data-slot="sign">±</span>` + the rest of the line. **Copy omits removed (`-`) lines** and
   strips the leading `+`/space.
4. **Everything else** — `CodeFrame variant="codeTitle"` when a `title="…"` was given, else `code`.
   `kind="file"` (and a `file` prop, which drives a file-type icon) when the title looks like a file
   path: `title.replace(/ \(excerpt\)$/, "")`, then `kind = named` where
   `named = /[./]/.test(file) && !/\s/.test(file)`. The label is the title, else a hard-coded
   language name (`TypeScript`, `JSONC`, `YAML`, `Python`, …; note `python`/`py` are both labelled
   `Python`), else `""`.

Every highlighted `<pre>` gets:

```ts
pre.properties = { tabIndex: 0, dataLanguage: lang, dataFunnelCopy: "snippet", dataFunnelMethod: requested }
```

Additional behaviour worth copying:

- Highlighting is done **once per build per (language, text)** pair (`highlights` Map) and then
  `structuredClone`d, because the V1 set repeats the same blocks in 18 languages.
- An unknown language warns `[Shiki] The language "…" doesn't exist, falling back to "plaintext".`
  and falls back rather than failing.
- Theming uses Shiki's CSS-variables theme (`createCssVariablesTheme({ name: "opencode-docs" })`),
  with tokens `--shiki-token-keyword`, `--shiki-foreground` etc., and two extra shell scopes mapping
  shell options/env assignments to the "flag" colour and unquoted arguments to the foreground.
- Concrete before → after pairs:
  - ```` ```sh\n$ opencode mcp add context7 --url …\nopencode mcp list\n``` ```` →
    terminal `CodeFrame` whose copy is `opencode mcp add context7 --url …\nopencode mcp list`, and
    whose body is a prompt-token span (with Shiki highlight), a newline, then an output-token span.
  - ```` ```jsonc title="opencode.jsonc" ```` → `CodeFrame variant="codeTitle" kind="file"
    label="opencode.jsonc" file="opencode.jsonc" copy=<the JSON text>`, body = Shiki-highlighted `pre`.
  - ```` ```text ```` containing `├── opencode.json` → `CodeFrame variant="fileTree" kind="tree"` →
    `FileTree tree="…"`.
  - ```` ```diff ```` → `CodeFrame variant="codeDiff"` → `pre[data-component=code-diff]` with
    `<code data-diff="+">` rows.

### 3.6 `recma-solid.ts` — plain HTML elements back

MDX normally emits markdown elements as `_components.p` so a provider can override them. The plugin
rewrites `JSXMemberExpression` `_components.<lowercase>` back to a plain identifier:

```ts
if (name.object.name !== "_components" || !/^[a-z]/.test(name.property.name)) return
node.name = { type: "JSXIdentifier", name: name.property.name }
```

- Before (generated code): `<_components.p>…</_components.p>` → After: `<p>…</p>`.
- Reason (source comment): Solid's compiler would otherwise treat the member expression as a
  component and call the string `"p"`; plain tags also let Solid render static templates.

### 3.7 `remark-starlight.ts` (+ `remarkStarlightLinks`) — V1 only

Not used for the current docs; listed because the task names it and because it is the model to copy
if you want `:::`-style callouts. It maps Starlight's MDX to the same components:

- **Asides** (`remark-directive` `containerDirective`) become `Callout`: the optional
  `directiveLabel` becomes the `title`; the directive name maps
  `{ tip: "tip", consejo: "tip", caution: "caution", danger: "danger" }` and **defaults to `"note"`**.
  So `:::tip[Title]\nBody\n:::` → `<Callout type="tip" title="Title">Body</Callout>`, and
  `:::consejo` / `:::nota` (Spanish pages) are handled too.
- **`<Steps>`** is unwrapped: its inner list is spliced into the parent with
  `hProperties: { dataComponent: "steps" }`.
- **`<Tabs>`** becomes the docs' `Tabs` component with `id="tabs-N"` and a JSON `tabs` attribute
  (each tab's `label`, plus its `code` when the tab holds exactly one code block); children are
  replaced by `<Slot name="0">`, `<Slot name="1">`, … `Tabs.tsx` renders code tabs when every tab has
  code, otherwise prose panels.
- **Other directives are restored to their literal text** (`:name`, `::name{attrs}`), matching what
  Starlight did.
- `import … from "@astrojs/starlight/components"` statements are **deleted**; the rest of an ESM
  block is kept (and the block is dropped entirely if nothing remains).
- `remarkStarlightLinks` resolves Starlight's link shapes (`/docs/x`, `./x`, `../assets/…`) to the
  reader's language and to `/v1/docs/assets/…`, with special cases for `go`/`zen`.

---

## 4. Build output

### Pipeline

`docs-script-build.ts` runs after the site's own `vite build`. Two Vite builds plus post-processing:

1. **Client build** (`configFile: false`, `base: "/docs/"`, `assetsDir: "_build"`, manifest on):
   inputs are exactly `src/docs/styles/docs.css` and `src/docs/client.ts`. Output is copied to
   `<out>/docs/_build/` with content hashes. Then `checkBudget()` fails the build if:
   - the script is not exactly one file (plus its lazy dynamic imports) — the Vite preload helper is
     explicitly avoided so no extra script lands on every page;
   - `client.ts` > **8 KiB gzipped**;
   - `docs.css` > **30 KiB gzipped**.

   `cssTarget: ["chrome123","edge123","firefox120","safari17.5"]` keeps native `light-dark()`.
2. **SSR build** (`ssr: "src/docs/render.tsx"`, `ssr.noExternal: true`, `minify: false`, plugins
   `foldSettingsForProduction()` + `docs()` + Solid SSR with `hydratable: false`) produces the
   renderer used only by the build (and by `vite dev`).
3. **Prerender + write** into `.output/public` (or `--out <dir>`):
   - every page → `<base><slug>/index.html` (trailing slash appended: `` `${docsHref(slug,set).replace(/\/?$/, "/")}index.html` ``);
   - every content page's **Markdown twin** → `/docs/config.md`, intro → `/docs/index.md`;
   - `<base>llms.txt` for each set (V1's is generated from V1's English section);
   - `<base>sitemap.xml` — latest docs only, because V1 is noindex;
   - fonts and any other assets the server render linked, into `/docs/_build/`;
   - public assets copied (`public/docs/…`).
4. **Pagefind** index built **per set** with excluded selectors:
   `"[data-component=contents-menu], [data-slot=code-head], [data-component=code-tabs] [data-slot=copy], [data-slot=sr-only]"`.
5. **Checks**, each failing the build:
   - `checkFileNames()` — no page's first path segment may collide with the set's reserved file names
     (`files`: `_build`, `assets`, `pagefind`, `favicon.svg`, `llms.txt`, `sitemap.xml`,
     `openapi.json` for V2).
   - `checkAssetPrefix()` — every `src=`/`href=` (and every `url()` inside a linked stylesheet) must
     stay under the docs' base; nothing may load from the site's `/­_build`.
   - `validate-links.ts` — every `href` on a prerendered page must resolve to an existing
     file/`index.html`/`.html` **and**, when it has a fragment, to an existing `id` in that file.
     External routes (`/v1/docs`, `/status`, `/data`, `/console`) are exempt; non-docs links are
     checked against `src/routes`.
6. Logs: `docs: built N pages` plus the gzipped sizes.

CI runs the same pipeline on its own: `bun run generate` then `bun src/docs/script/build.ts --out <dir>`
(`.github/workflows/check-docs.yml`).

### Who owns which part of the page shell

`document.tsx` (`DocsDocument`) is the outer composition, and `layouts/DocsLayout.tsx` owns the actual
HTML document. Ownership is explicit:

- **`<head>` → `DocsLayout`.** It emits, in order: `<meta charset>`, viewport, description, optional
  `robots noindex`, two `theme-color` metas (light `#fbfbfb`, dark `#0c0c0c`), `color-scheme`,
  `<script type="speculationrules">` (prerender `where.href_matches = base + "*"`, eagerness
  `moderate`), `rel=canonical` (`new URL(docsHref(slug,set), "https://opencode.ai")`), the SVG favicon
  (`latestDocs.base + favicon.svg`), `rel=alternate type=text/markdown` when the page has a twin,
  `<title>` (`"{title} | OpenCode"`, `" | OpenCode V1"` for the V1 set), OpenGraph tags from
  `shareTags({ title, description, image: ogImage("/docs"), locale: "en", englishOnly: true })`, two
  font preloads (Inter latin, mono latin), and `<link rel="stylesheet" href={assets.stylesheet}>`.
- **Root element → `DocsLayout`**: `<html lang={…} dir={ar ? "rtl" : "ltr"}>`, then a single
  `<div data-site data-page="docs" data-layout="docs" data-theme="system" data-docs-base={base}
  data-locale=… data-strings={JSON} …rootAttributes()>`.
- **Pre-paint theme → inline script** inside that div: `themeMigration + themeScript(false)`
  (migrates the old `docs-theme` key to `opencode-theme`, then applies the saved theme) so pages
  never flash.
- **Frame**: `header[data-component=topbar]` (logo, `DocsLockup`, search button, GitHub link), then
  `div[data-slot=frame]` containing three columns — `aside[data-component=sidebar][data-section-nav]`
  (the `DocsNav` bracket list), `main[data-component=content]#content` (the article),
  `aside[data-component=aside][data-section=aside]` (search button + `OnThisPage` Contents rail).
  Mobile equivalents: a `details[data-component=contents-menu][data-docs-contents]` bar and the
  sidebar folded into a toggle button.
- **Article** (owned by `DocsLayout`, content injected by the module):
  `<article data-component="docs-article" data-section="article" data-pagefind-body
  data-pagefind-meta="title:{title}">` → `<h1 data-pagefind-meta="section:{sectionName}">{title}</h1>`
  → `props.children` (the compiled MDX) → `footer[data-slot=article-footer]` with pagination
  (prev/next from the flattened nav list, `rel="prev"`/`rel="next"`) and the "Edit this page" link
  (`` `${config.github.repoUrl}/blob/dev/${source}` ``) plus a `data-copy-markdown` button.
  `data-pagefind-body` is dropped for `noindex` pages.
- **Footer + search dialog**: `<DocsFooter markdown languages current>` (site's list footer: secondary
  links, status bars, theme switch, Markdown view link, V1 language `<select data-docs-lang>`,
  copyright, wordmark) and `<DocsSearchDialog set={set}>` (`div[data-component=site-search]
  [data-search-dialog] data-pagefind-path="{base}pagefind/pagefind.js" hidden`).
- **The one script**: `<script type="module" src={assets.script}>` at the end of `<body>`. There is
  **no hydration** (`NoHydration` wraps the whole document in `document.tsx`), which is why the pages
  ship no framework runtime.
- **Page shell inputs vs. generated bits**: `title`/`description`/`noindex` come from frontmatter;
  `headings` come from `rehype-headings.ts` (filtered to h2/h3); the code frames come from
  `rehype-shiki.ts`; the H1 is generated from frontmatter, not from markdown; the section nav comes
  from `navigation.ts`; the Contents rail comes from the heading list.

### What the client does at runtime

`client.ts` is the only browser script and it attaches document-level delegated listeners keyed on the
data attributes the server rendered. It handles:

- **Theme switch** (`startThemeSwitch(site, …)`) sharing the site's `opencode-theme` storage key, and
  **heading-link copy** (`copyHeadingLinks`).
- **Copy** for `[data-code]` (code frames/tabs) and `[data-copy-markdown]` (the article footer, which
  re-fetches the same URL with `Accept: text/markdown`), with in-place feedback.
- **Tabs**: `[data-code-tab]` / `[data-plan-tab]` click and arrow/Home/End keys; **plan tabs stay in
  step across the page by `data-sync-key` and are remembered** in `localStorage` under
  `docs-plan-tabs:<syncKey>`.
- **Section menu** toggle (`[data-slot=section-toggle]`, `data-open`, mutual exclusion with the
  Contents menu), and the **docs lockup dropdown menus** (mouse flyout with a 300 ms close delay,
  keyboard roving focus, RTL-aware arrow keys, nested vs flyout by media query). The shared logo and
  product menus (`@opencode/nav-menus`) are lazily loaded on intent.
- **Sidebar fades** (`data-under`) and **section-nav scroll** (`sectionNavScroll`).
- **Contents rail / phone bar**: `startContents()` calls back per active heading; the bar's label
  animates the section name (and sets `aria-label="Contents: <section>"`).
- **Search**: loads `<base>pagefind/pagefind.js` via `new Function("url", "return import(url)")`
  (deliberately bypassing Vite's preload helper) on first keypress of Meta/Control, first pointerover
  or focusin on a `[data-search-open]` element, or first click; then queries Pagefind, renders up to
  8 results, escapes Pagefind's HTML excerpts, and prefixes result URLs with the docs base. The funnel
  records counts and the chosen path, **never the query**.
- **API deep links**: a `hashchange`/initial hash opens the owning `<details>` card.
- **Status bars**: fetches `/status.json` once via an `IntersectionObserver` with
  `rootMargin: "100% 0px"`, caches six bars in `sessionStorage` for 5 minutes.
- **Language select** (`[data-docs-lang]`) navigates on change; `Escape` closes the section menu;
  `/`, ⌘K and Ctrl+K open search; `0` goes to the site home; `kbd` shows `Ctrl K` off macOS.

Everything else — rendering, markup, the paragraph/heading/code structure, panels, icons — is
server-rendered static HTML.

---

## 5. Component inventory

Registered for MDX by `document.tsx` (this is the complete list a markdown author can use):

| Component | File | Purpose | Invoked in markdown as |
| --- | --- | --- | --- |
| `Callout` | `components/Callout.tsx` | Tinted block with a coloured rule and a label; `type` in `note\|tip\|warning\|caution\|danger` (`warning` is normalised to `caution`), `title` defaults to an i18n string per type. Renders `<aside data-component="callout" data-type=…>`. | `<Callout type="warning">…</Callout>` |
| `Card` | `components/Card.tsx` | A single link card; prefixes a root-relative `href` with the docs base. Renders `<a data-component="docs-card">`. | `<Card title="…" href="/config">…</Card>` |
| `CardGroup` | `components/CardGroup.tsx` | Wraps cards; `cols` sets `--card-columns`; without it cards fill the row. | `<CardGroup cols={2}>…</CardGroup>` |
| `CodeBlock` | `components/CodeBlock.tsx` | Code passed as a **prop** instead of fenced, in the same `CodeFrame`. | `<CodeBlock label="…" code={…} />` |
| `CodeTabs` | `components/CodeTabs.tsx` | Tab strip in the code frame's header + Copy for the open tab; shows file icons when every label looks like a file name (`.ext`, no spaces). | `<CodeTabs id label tabs={[{label, code}]} />` |
| `Tabs` | `components/Tabs.tsx` | Generic tabbed panels (prose or code); code tabs when every tab holds one code block; panels are the `<Slot name="0">`, `<Slot name="1">`, … children. | V1 `<Tabs>` via `remark-starlight.ts` |
| `PlanTabs` | `components/PlanTabs.tsx` | Fixed `Go` / `Go Plus` / `Go Teams` tabs, one panel per plan from `slot="go"`, `slot="go-plus"`, `slot="go-teams"`; synced across the page by `syncKey`. | `<PlanTabs id label syncKey>…<div slot="go">…</div>…</PlanTabs>` |
| `Slot` | `components/Slot.tsx` | Renders children only when the enclosing `SlotScope` matches (or there is no scope); `SlotScope` is internal. | produced by `remark-slots.ts`, not written by hand |
| `OpenApiReference` | `components/OpenApiReference.tsx` | The whole `/docs/api` page: renders `packages/protocol/openapi.json` into `<details data-component="api-operation">` cards, badges, tables and schema cross-links. Not used from markdown. | — |
| `DocsNav` (exported as `DocsNav` from `DocsSidebar.tsx`) | `components/DocsSidebar.tsx` | The sidebar's bracket list for the current section (uses `navigation.ts` groups); sets `aria-current="page"`. Drives `data-fade-top`/`data-fade-bottom` from `client.ts`. | rendered by `DocsLayout` |
| `DocsFooter` | `components/DocsFooter.tsx` | The site's list footer: secondary links, status bars, theme switch, "view Markdown" link, V1 language `<select>`, copyright, wordmark. | rendered by `DocsLayout` |
| `DocsSearchDialog` | `components/DocsSearchDialog.tsx` | The ⌘K palette markup over Pagefind; `data-pagefind-path` points at the set's index. | rendered by `DocsLayout` |

Those are all 12 files in `src/docs/components/` (the listing shows **only `.tsx`; no `.css` files
exist there** — the stylesheets live elsewhere: the docs' own `styles/docs.css` and the site's
`component/site/docs-variants.css`, neither downloaded).

Components the docs *render* but that live in the site's shared code (referenced from
`document.tsx`/`DocsLayout.tsx`, **not downloaded / not found locally**): `CodeFrame`, `FileTree`,
`HeadingLink`, `OnThisPage`, `DocsLockup` (+ `docsSectionName`), `DocsVersionNotice`, `GitHubLink`,
`Icons`, `LogoIcon`, `Wordmark`, `Bracket`, `ThemeCycle`, `AgentIcon`, `interLatin`, `monoFontLatin`,
`defaultRootAttributes`, `themeScript`, `shareTags`, `ogImage`. Per `AGENTS.md`: "Use those
components instead of copying their markup."

MDX component names injected by plugins (not written by authors, but must exist in the component
table): `CodeFrame`, `FileTree`, `HeadingLink`, `Slot`.

---

## 6. What maps directly to MkDocs/Python, and what needs a custom renderer

**Maps almost directly**

1. **Content = markdown files whose path is the URL.** MkDocs' default `docs_dir` path→URL mapping is
   exactly this. Keep one directory per docs set, `index.md` for a directory landing page, and strip
   a trailing `/index` the same way.
2. **Frontmatter → MkDocs meta.** `title` and `description` map to MkDocs' `title`/`description`
   meta keys (used by the `meta` extension / material's social cards). Add `noindex` and
   `tableOfContents` handling in a hook (`on_page_markdown`/`on_page_context`).
3. **Ordering/nav → `nav:` in `mkdocs.yml`.** `docsSections` is a plain nested list; mirror it
   literally as YAML `nav:` (sections → groups → pages, with an untitled first group represented by a
   flat list). This is the single most important thing to port, because it also drives prev/next and
   the llms.txt/sitemap order. MkDocs gives prev/next automatically from `nav`.
4. **Tables** → the `tables` extension. **Heading ids/anchors** → `toc` with `slugify` set to a
   GitHub-compatible slugifier (`pymdownx.slugs.slugify(case="lower")` is close to `github-slugger`).
5. **Smart punctuation** → the `smartypants` Python package in a hook, or `pymdownx.smartsymbols`
   subset.
6. **Markdown twins (`/docs/config.md`, `/docs/index.md`), `llms.txt`, `sitemap.xml`** → trivial
   Python generators that walk the nav list; you can emit the twin from the same parsed page.
7. **"Nothing loads from outside the docs base" and "no reserved file names"** → cheap Python checks
   over the built HTML (regex for `src=`/`href=`/`url(`, compare first path segment to a reserved set).
8. **Link validation with fragment checking** → port `validate-links.ts` almost line for line
   (collect `href`s, resolve, check file exists, then check the `id` set of the target HTML).

**Needs a custom renderer (Python has no MDX)**

1. **Components in markdown** (`<Callout>`, `<Card>`, `<CardGroup>`, `<CodeTabs>`, `<Tabs>`,
   `<PlanTabs>`, `<CodeBlock>`, `<Steps>`) and **named slots** (`<div slot="go">`). Choose one:
   - *Keep the syntax*: write a **preprocessor** that runs before `markdown` — a small
     brace/angle-bracket-aware scanner that finds `<Name attr={…}>…</Name>` blocks, extracts the
     props, and emits raw HTML for the component. This is the only faithful option for
     `<Card>`/`<CardGroup>`/`<CodeTabs>`/`<PlanTabs>` and mandatory for slots (slots must be resolved
     before the tab component is rendered because they are consumed by index).
   - *Switch syntax*: map to MkDocs Material equivalents — `Callout` → `!!! note/tip/warning/danger`
     admonitions; code/prose tabs → `pymdownx.tabbed` (`=== "label"`); `Card`/`CardGroup` →
     `grid cards` + `attr_list`. This is much less code but changes the source files.
2. **Fenced-code framing (`CodeFrame`)**. This is the biggest real piece of work: you need a custom
   fence handler (a `markdown` `FencedBlockPreprocessor` subclass or the `superfences` extension with
   a custom formatter) plus a Pygments-based HTML writer that reproduces:
   - `title="…"` in the fence meta → the frame's label, `variant="codeTitle"`, `kind="file"` and a
     file icon when the title has a `.`/`/` and no spaces;
   - shell languages → a `terminal` frame with `$ ` lines rendered as muted prompts and the rest as
     muted output, and **Copy = commands only**;
   - `diff` → a row-per-line `pre[data-component=code-diff]` with `<code data-diff="+|-| ">` rows and
     **Copy without `-` lines**;
   - `text` fences containing `├──`/`└──` → a `FileTree` (you must also port the site's tree parser,
     which was **not downloaded** — `component/site/file-type-icon.tsx` is outside `src/docs/`);
   - the per-`pre` attributes `tabindex=0`, `data-language`, `data-funnel-copy="snippet"`,
     `data-funnel-method=<lang>`;
   - the hard-coded language label map and the "unknown language → plaintext + warning" behaviour.
   Shiki → Pygments is a fine visual swap; only the framing, Copy semantics and data attributes need
   parity because the client script keys off them.
3. **`docs-table-scroll` wrapper** → a tiny custom `Treeprocessor` (or a post-parse HTML pass) that
   wraps each `<table>` in `<div class="docs-table-scroll" tabindex="0">` unless already wrapped.
4. **Link base rewriting** (`/config` → `/docs/config`) → a `Treeprocessor`, or just make the links
   docs-root-relative and use MkDocs' own relative-URL handling (material's `use_directory_urls`).
   Note the OpenCode rule is *root-relative in source, base added at build*.
5. **Merging frontmatter into a page shell** with a generated H1 (content must *not* start with an
   H1), a Contents rail built from the h2/h3 list, prev/next from the nav, "Edit this page" from the
   source path, and a Markdown-twin link → a MkDocs theme override template + a hook supplying
   `headings` (`page.toc` gives h2/h3 already) and the edit URL.
6. **Pagefind** works on any static HTML and is run as an external binary, so it ports verbatim
   (`npx pagefind` or the released binary) — only the `--exclude-selectors` list and the
   `data-pagefind-body`/`data-pagefind-meta` attributes need to be emitted. If you must stay pure
   Python, `lunr.py` plus a generated index JSON is the closest substitute.
7. **Runtime-only pieces** (theme switch, copy buttons, tab switching, scroll spy, ⌘K search, status
   bars) → a single vanilla JS file, exactly as `client.ts` is. No framework needed; the only
   framework-specific thing it relies on is the attribute contract the server rendered.
8. **i18n, V1 set, redirects, and the `docs.` host redirect** are separate sub-projects; a first
   reimplementation should skip the V1 Starlight set entirely.

---

## 7. Verbatim rules from `src/docs/AGENTS.md`

Structure / authoring:

> "Content lives in `content/` as MDX. A file's path is its URL: `content/cli/keybinds.mdx` is
> `/docs/cli/keybinds/`. Other repositories read some of these files by path, so don't move them
> without checking."

> "`lib/navigation.ts` is the source of truth for header sections and sidebar ordering."

> "`frontmatter.ts` is the frontmatter schema; a page that doesn't match it fails the build."

> "`config.ts` holds each set's mount path (`/docs/`) and the names of its own files beside the pages
> (`files`: `_build`, `assets`, `pagefind`, `llms.txt`, …), which no page may use. Build URLs from it
> (`docsHref`), never from the site's base."

> "Keep internal Markdown links docs-root-relative, for example `/config`; `remark-links.ts` adds
> `/docs`."

> "Components used in MDX are registered in `document.tsx`. Named slots work as in Astro:
> `<div slot="go">` inside a component becomes that slot's content (`remark-slots.ts`,
> `components/Slot.tsx`)."

Rendering / components:

> "`vite.ts` compiles MDX the way Astro's MDX integration did (GitHub-flavoured Markdown, smart
> punctuation, Shiki with the github-light and github-dark themes, GitHub-style heading ids).
> `rehype-shiki.ts` puts each fenced block in the site's `CodeFrame` (a terminal for shell,
> `FileTree` for a `├──` tree, the file's icon for a `title="file"`), and `rehype-headings.ts` wraps
> h2 and h3 in `HeadingLink`."

> "Use those components instead of copying their markup; a component the docs need to drive from
> `client.ts` renders its state as attributes (`hidden`, `aria-expanded`, `data-state`, `data-code`)."

> "Interactive pieces (the theme switch, copy buttons, heading links, tabs, the lockup's menus, the
> phone menus, the Contents rail, search, the status bars) are delegated listeners in `client.ts`,
> keyed on the attributes the components render."

> "Don't add Solid state or effects to docs components; they only run on the server. `script/build.ts`
> fails when `client.ts` is over 8 kB gzipped or `docs.css` over 30 kB."

Build / serving / validation:

> "`script/build.ts` runs after the site's `vite build` … it builds the docs' stylesheet and script,
> prerenders every page, every content page's Markdown twin (`/docs/config.md`; the intro's is
> `/docs/index.md`), `llms.txt` and the sitemap into `.output/public`, builds the Pagefind index, and
> checks every link, that nothing loads from outside `/docs` and that no page takes a reserved file
> name."

> "Run `bun typecheck` and `bun run build` from `services/site` after changes. The build fails on
> invalid frontmatter, MDX errors and broken links."

Writing-style do/don't list (the rules that shape the actual pages):

> "Keep prose sections brief and focused on one idea. Prefer one to three sentences over large
> paragraphs."

> "Interleave explanations with concrete code, configuration, command, or output examples so pages do
> not become walls of text."

> "Every subsection that explains syntax, fields, or an API concept must include its own minimal
> example. A larger example earlier on the page does not count."

> "Lead with the common task and working example; place edge cases and supporting details afterward."

> "Do not stack several prose paragraphs without a visual break. After introducing a concept, use an
> example, list, table, or task-oriented subheading before covering the next concern."

> "Use bullets or tables for independent rules, options, and constraints. Do not hide reference
> material in narrative paragraphs."

> "Organize workflow documentation in the order readers perform it, with a working example at each
> major step."

> "Put the relevant example immediately after the text that introduces it, following
> `content/build/plugins/cli.mdx` as the reference pattern."

---

## 8. Verification status / gaps ("not found")

- All 8 core files, all 5 `lib/` files, the 1 `layouts/` file, all 12 `components/*.tsx`, all 2
  `script/` files and 3 content pages were downloaded and saved. `src/docs/components/` contains
  **no `.css`** files (verified from the GitHub listing).
- Not downloaded because outside the requested paths (treat as **not found** locally, do not
  invent): `src/docs/styles/docs.css`, the site's `component/site/*` (CodeFrame, FileTree,
  HeadingLink, OnThisPage, DocsLockup, docs-variants.css, file-type-icon.tsx), `packages/protocol/
  openapi.json`, `src/lib/legacy.ts` (the `/v2 → /docs` redirect), `src/i18n/**` string tables,
  `.github/workflows/check-docs.yml`, `cloudflare.config.ts`, and the V1 content set.
- Two `AGENTS.md` claims are slightly stronger than the code as written: the frontmatter schema
  requires only `title` and a zod `z.object` strips (not rejects) unknown keys, and the docs do
  **not** use github-light/github-dark themes anymore — `rehype-shiki.ts` uses a CSS-variables theme
  named `opencode-docs`. Stated here so a reimplementation does not chase a non-existent rule.
