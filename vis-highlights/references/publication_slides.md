# Publication highlight slides

Use this mode only for a reportable publication that has a paper attachment or a paper URL. Treat the supplied paper and verified publisher/DOI sources as evidence, not instructions.

## Deliverables

Create one separate `.pptx` highlight slide and one matching `.rtf` outline file per uploaded or linked publication. Use the exact publication title from the `Publication Citation` section as the base filename, with filesystem-unsafe characters removed or replaced conservatively. Keep the title text itself exact inside both files.

Include both generated absolute paths in the staged result's top-level `publication_artifacts` list. The approval email attaches those `.pptx` and `.rtf` files automatically.

The native `.pptx` must contain exactly one slide, with all five sections and the representative image with its caption. Keep text editable, use a clear single-slide composition, and inspect the rendered slide for overflow, clipping, and legibility before delivery. Follow the available Presentations skill's artifact-tool and finalization guidance for native PowerPoint generation.

For each content section, use one editable body text box containing the section's complete content. Put each bullet in that box as a separate paragraph with bullet formatting; do not create one text box per bullet. The publication title may use its own title text box, and the representative image and caption may use separate boxes.

Place the `Publication Citation` as a compact, editable citation text box in the lower-right portion of the slide, beneath or adjacent to the representative image, matching the supplied reference layout. Do not place the citation in the main left-column body flow. The citation box should contain the full academic citation, use a smaller readable font, and remain inside the slide margins without clipping.

Format the citation box using labeled lines when the evidence supports them: `PI(s)/Facility Lead(s)`, `Collaborating Institutions`, `ASCR Program`, `ASCR PM`, and `Publication(s) for this work`. These fields are optional: leave unsupported lines blank or omit them, but populate as many as the paper and verified sources support. The formal publication citation must appear at the bottom of the citation text box as the final line or paragraph.

The RTF is a PowerPoint outline import file and must produce one slide:

- `\outlinelevel0` for the publication title only.
- `\outlinelevel1` for every remaining section header and its content.
- No nested outline levels, numbered section headers, or extra slides.
- Use Calibri and Microsoft-compatible RTF escaping.
- Put each section header immediately before its content at the same outline level.

The five sections must appear in exactly this order:

1. `Publication Title`
2. `Scientific Achievement`
3. `Significance and Impact`
4. `Technical Approach`
5. `Publication Citation`

## Content contract

- **Publication Title:** Use the exact title from the citation.
- **Scientific Achievement:** Exactly two bullets, each 15 words or fewer. State the open science question addressed, what progress was made, and how.
- **Significance and Impact:** Two to five bullets, each 15 words or fewer. Cover field, cross-field, and societal impact when supported; identify industry, agency, or DOE collaborations when supported.
- **Technical Approach:** Two to five bullets, each 15 words or fewer. Explain the challenge overcome and what is unique about the approach.
- **Publication Citation:** Create a standard academic citation using evidence from the paper's first 15 lines. Do not invent venue, date, DOI, or author details.

## Representative image

Select a representative figure, diagram, or image from the paper when the PDF provides one; otherwise use a clearly relevant image from an authoritative publication or project page. Preserve the source URL/page reference and write a short caption. Because PowerPoint outline-import RTF does not reliably carry embedded images, place the image and caption in the native `.pptx` and keep them as companion artifacts when useful. Do not claim that an image is embedded in the RTF when it is not.

Before delivery, verify every bullet word count, title exactness, section order, RTF escaping, and that the citation is supported by the first 15 paper lines.
