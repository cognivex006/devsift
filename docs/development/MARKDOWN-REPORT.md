# Standalone Markdown reports

`devsift.markdown_report.render_markdown(report: Report) -> str` consumes the
accepted sealed report model. Dictionaries, serialized findings and arbitrary
objects are rejected. It returns one deterministic standalone Markdown document
and performs no file, Git, native, network, remediation or publication operations.
Writing/publishing the returned string is a separate explicit workflow.

The summary links to complete inline case sections. Every case includes identity,
severity/confidence, lifecycle/enforcement/security escalation, approval/autofix,
fingerprint, source proof and symbol/region status, related/runtime evidence,
BEFORE, AFTER (PROPOSAL), detector explanation/invalidating exceptions,
alternatives, both-sided impact/risk and their evidence, affected scope,
consumers/tests, verification/rollback and full review/implementation prompts.
Cases are retrieved through the model's case lookup; none are truncated into a
preview or hidden behind a missing dashboard/file. Prompts have stable internal
anchors and remain inert fenced text, not executable buttons or auto-actions.

BEFORE displays only the model's verified selected region, not invented full file
lines or surrounding source. Prefixes number the actual physical LF lines from
the proven start region. CRLF separators are retained between displayed selected
lines; exclusive end coordinates remain explicit metadata. Emoji is retained.
Unicode format/bidi/line-separator characters and unsafe controls are rendered as
visible escapes so they cannot spoof layout or lines. This display transformation
does not modify the model's immutable evidence. Tabs and physical LF/CRLF in code
are retained; a lone CR is escaped. All shown selected lines belong to the finding
region; no additional highlighting scope is guessed.

An existing whole-region `[REDACTED]` remains one whole marker. For a multiline
region it carries the proven line-range label, without inventing per-line masked
contents. The renderer never re-reads raw source or re-masks protocol words, and
cannot recover withheld content. It relies on accepted model redaction; it must
not be used to turn untrusted unredacted dictionaries into public reports.

When source is unresolved the report states SOURCE_UNRESOLVED, its reason and
lookup plan. No file/line zero, source SHA, BEFORE snippet, local link or guessed
repository URL is supplied. Navigation appears only when the sealed model already
provides a source-proven, encoded HTTPS repository link. No `file://` links,
working-tree/commit equivalence or new navigation are synthesized here.

Untrusted repository/path/prose values escape Markdown punctuation, HTML,
controls and automatic-link delimiters. Code/proposal/prompt blocks use dynamic
fences longer than every backtick run in their contents. Source HTML and apparent
Markdown actions remain inert code. Fixed model keys/enums and template labels
retain their meaning even if a caller's earlier redactor knew words such as
unknown/source/pending; this renderer does not mask those constants again.

Unknown risk remains unknown and is never relabeled safe. Pending proposals remain
explicitly pending, with no invented patch. Security-review flags retain their
independent follow-up meaning even when a completed gate is nonblocking. No
approval or tests are asserted from generated prose. The document is bounded to
16,000,000 UTF-8 bytes; excess or unsupported input raises static MarkdownError
rather than returning a truncated case/report. Contextual recommendations are
currently empty in the accepted producer model; nonempty contextual data requires
the report assembly integration instead of being silently discarded.

`test_markdown_report.py` uses actual temporary Git proof, independent full-case
contract fixtures, safe navigation, malicious Markdown/HTML/backtick/Unicode
content and source/Git byte snapshots. A controlled adapter reports HC002 and an
overlapping LOG001 region through scan -> source-reproved report -> Markdown,
proving the existing whole security mask survives end to end. This fixture tests
rendering/provenance, not an additional native detector claim. Unresolved/empty
incomplete reports, reserved redactor words, fresh outputs, strict input and byte
limits are also checked.
