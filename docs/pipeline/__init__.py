"""The v2 build pipeline: one module per step of the docs build.

Mirrors ``services/site/src/docs`` upstream, where each transform is its own
module (``frontmatter.ts``, ``rehype-headings.ts``, ``rehype-shiki.ts``,
``script/build.ts``). See ``reference/PIPELINE.md`` for that mapping.
"""
