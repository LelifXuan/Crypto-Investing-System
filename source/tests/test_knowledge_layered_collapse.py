"""Static guards for the knowledge page's three-tier collapse model.

Layered collapse (2026-08-18):
1. Section level  — `.knowledge-section-card.is-collapsed` shows one compact
   `<eyebrow / 标题 / 条目数 / 展开按钮>` row; the entry list
   (`.knowledge-entry-list`) is `hidden`.
2. Guide level    — `.knowledge-guide-card.is-collapsed` shows only the
   header row + chevron; `.knowledge-guide-body` is `hidden`.
3. Term level     — `.knowledge-item-card.is-open` reveals the lazily
   injected `.knowledge-body`. Default is collapsed.

Each layer owns its own collapsed state set in `state` (collapsedSections
/ collapsedGuides) plus the card-level is-open / is-collapsed className.

These guards pin:
- Render path uses `is-collapsed` (not just `hidden`) so CSS can shape
  the collapsed look (no card chrome, no padding, no summary)
- Both default classes are emitted on first render (the user's complaint
  was that everything was pre-expanded by default)
- `data-toggle-section` / `data-toggle-guide` / `data-toggle-knowledge`
  are all wired up so the delegation layer can find them
- Hash navigation (`#section-xxx` and `#term-id`) auto-expands ancestors
  via `expandSection` / `expandAncestorsForCard`
- Guide card no longer renders `is-open` by default (the regression that
  made '页面使用指南' permanent open)
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "knowledge.js").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")
STYLES = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# JS render layer
# ---------------------------------------------------------------------------


def test_render_sections_emits_is_collapsed_class_when_section_folded() -> None:
    """renderSectionsHtml() must emit both `is-open` and `is-collapsed` on
    `.knowledge-section-card`. The default is `is-collapsed` because the
    Set holds 'user-opened' ids — an empty Set on first render means every
    section is in its default (collapsed) state. The class string is
    built from `isOpen`, which inverts the Set check."""
    assert 'class="knowledge-section-card ${isOpen ? "is-open" : "is-collapsed"}"' in PAGE, (
        "knowledge-section-card must toggle between is-collapsed / is-open "
        "based on state.collapsedSections membership (Set holds OPEN ids)"
    )


def test_render_sections_emits_section_toggle_button_with_data_attr() -> None:
    """The section header owns one explicit right-side toggle button."""
    assert "data: { toggleSection: section.id }" in PAGE, (
        "section toggle must carry data-toggle-section attribute for "
        "event-delegation"
    )
    assert "knowledge-section-toggle" in PAGE, (
        "knowledge-section-toggle class missing — click delegation won't "
        "find the toggle without it"
    )
    assert 'class="knowledge-section-header"' in PAGE
    assert 'class="knowledge-section-controls"' in PAGE
    assert 'variant: "section-compact"' in PAGE
    assert 'expandLabel: "展开"' in PAGE
    assert 'collapseLabel: "收起"' in PAGE


def test_collapsed_section_has_no_term_preview_pills() -> None:
    """Category bars stay compact instead of repeating term names."""
    assert "knowledge-section-preview" not in PAGE
    assert "knowledge-section-pill" not in PAGE


def test_render_sections_emits_hidden_entry_list_when_collapsed() -> None:
    """When a section is collapsed, the entry list element must carry the
    `hidden` attribute so screen readers and `display: none` rules skip
    the content. JSX template uses `${isOpen ? "" : "hidden"}`."""
    assert 'id="section-body-${escapeHtml(section.id)}" ${isOpen ? "" : "hidden"}' in PAGE, (
        "section-body wrapper must set `hidden` attribute when section "
        "is collapsed so assistive tech skips the entries"
    )


def test_render_guide_emits_is_collapsed_class_when_guide_folded() -> None:
    """renderGuideCard() must default to `is-collapsed` (not `is-open`)
    — V1.5.x had the regression that all '页面使用指南' cards were
    permanently expanded. The user explicitly asked for the same
    'title-only' default as regular sections."""
    assert 'class="knowledge-guide-card ${isOpen ? "is-open" : "is-collapsed"}"' in PAGE, (
        "knowledge-guide-card must toggle is-open / is-collapsed based "
        "on state.collapsedGuides (Set holds OPEN ids)"
    )
    # Old default-expanded path must be gone — the literal 'class="knowledge-guide-card is-open"'
    # should never be the unconditional class string (it would mean the
    # guide is always expanded).
    assert 'class="knowledge-guide-card is-open"' not in PAGE, (
        "knowledge-guide-card must not unconditionally render is-open — "
        "default state should be is-collapsed to match section level"
    )


def test_render_guide_emits_toggle_button_with_data_attr() -> None:
    """Guide cards must wrap their header in `<button data-toggle-guide="…">`
    so click delegation can find them. The guide-body wrapper must also
    carry `hidden` when collapsed."""
    assert 'data-toggle-guide="${esc(item.id)}"' in PAGE, (
        "guide toggle must carry data-toggle-guide attribute for "
        "event-delegation"
    )
    assert 'id="guide-body-${esc(item.id)}" ${isOpen ? "" : "hidden"}' in PAGE, (
        "guide-body wrapper must set `hidden` when guide is collapsed"
    )


def test_click_delegation_handles_three_layers() -> None:
    """The single click delegation on `.knowledge-sections` must dispatch
    to all three toggle paths: data-toggle-section (chapter),
    data-toggle-guide (page guide card), data-toggle-knowledge (term)."""
    # Section path
    assert "sectionButton && sectionsEl.contains(sectionButton)" in PAGE, (
        "click delegation must recognise section toggles"
    )
    # Guide path
    assert "guideButton && sectionsEl.contains(guideButton)" in PAGE, (
        "click delegation must recognise guide toggles"
    )
    # Term path (legacy)
    assert 'target.closest("[data-toggle-knowledge]")' in PAGE, (
        "click delegation must still recognise term toggles"
    )


def test_state_collapsed_sets_are_initialised_empty() -> None:
    """state.collapsedSections and state.collapsedGuides must start as
    empty Sets so first render defaults every section / guide to
    collapsed. The previous version had no collapse state at all and
    rendered everything pre-expanded."""
    assert "collapsedSections: new Set()" in PAGE, (
        "state.collapsedSections must be an empty Set on first render — "
        "any pre-populated id would default that section to expanded"
    )
    assert "collapsedGuides: new Set()" in PAGE, (
        "state.collapsedGuides must be an empty Set on first render"
    )


def test_reset_state_clears_collapsed_sets_on_spa_remount() -> None:
    """resetState() — called from unmount() — must clear both collapse
    Sets so returning to the page starts fresh (everything collapsed),
    not with stale 'already expanded' state from the previous session."""
    assert "state.collapsedSections.clear()" in PAGE, (
        "resetState() must clear state.collapsedSections so the next "
        "mount defaults to fully-collapsed"
    )
    assert "state.collapsedGuides.clear()" in PAGE, (
        "resetState() must clear state.collapsedGuides"
    )


def test_focus_hash_target_expands_ancestor_section() -> None:
    """focusHashTarget() must call expandAncestorsForCard() before
    openTermCard() so a hash pointing at a term auto-opens the section
    and (if relevant) the guide card holding it. Without this, deep
    linking from tooltips / related_terms would scroll to a hidden
    element behind a collapsed section."""
    assert "expandAncestorsForCard(card)" in PAGE, (
        "focusHashTarget() must call expandAncestorsForCard(card) to "
        "auto-open the owning section and guide"
    )


def test_focus_hash_target_handles_section_hash() -> None:
    """focusHashTarget() must also handle `#section-xxx` hashes from
    the left-rail section navigation — those should expand the section
    (if folded) and scroll to the title, not try to open it as a term."""
    assert 'if (rawHash.startsWith("section-"))' in PAGE, (
        "focusHashTarget() must short-circuit on #section-… hashes"
    )
    assert "expandSection(sectionId)" in PAGE, (
        "focusHashTarget() must call expandSection() for chapter hashes"
    )


def test_section_toggle_updates_current_card_without_full_rerender() -> None:
    """Toggling must preserve focus and respond to rapid repeated clicks."""
    handler = PAGE[PAGE.index("const sectionButton ="):PAGE.index("// 使用指南")]
    assert "setSectionExpanded(sectionId, nextOpen)" in handler
    assert "updateKnowledgeContent()" not in handler
    assert "setDisclosureState(button, nextOpen)" in PAGE
    assert 'body.removeAttribute("hidden")' in PAGE
    assert 'body.setAttribute("hidden", "")' in PAGE


# ---------------------------------------------------------------------------
# CSS layer
# ---------------------------------------------------------------------------


def _css_block(css: str, selector: str) -> str:
    """Return the substring between the matched selector and the first
    closing brace at the same nesting depth. Comment-stripping is left
    to the caller when needed (knowledge-guide-card has no comments)."""
    idx = css.index(selector)
    depth = 0
    for cursor in range(idx, len(css)):
        ch = css[cursor]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return css[idx:cursor]
    return css[idx:]


def test_section_header_pins_single_toggle_to_the_right() -> None:
    """The compact header uses title-left / controls-right geometry."""
    header = _css_block(
        EDITORIAL,
        'body[data-page="knowledge-base"] .knowledge-section-header {',
    )
    toggle = _css_block(EDITORIAL, "body .disclosure-toggle {")
    compact = _css_block(
        EDITORIAL,
        "body .disclosure-toggle.disclosure-toggle--section-compact {",
    )
    assert "grid-template-columns: minmax(0, 1fr) auto" in header
    assert "min-height: 66px" in header
    assert "display: inline-flex" in toggle
    assert "height: var(--disclosure-height)" in toggle
    assert "--disclosure-min-width: 82px" in compact
    assert "transform: scale(0.96)" in EDITORIAL
    assert "transition: all" not in toggle


def test_section_toggle_paints_chevron_rotation() -> None:
    """Collapsed shared controls point right; expanded controls point down."""
    assert '.disclosure-toggle[aria-expanded="false"]' in EDITORIAL
    assert "rotate(-90deg)" in EDITORIAL


def test_guide_toggle_is_grid_button() -> None:
    """.knowledge-guide-toggle must be a button laid out as a 1fr auto
    grid (same shape as the section toggle, just smaller padding)."""
    assert ".knowledge-guide-toggle {" in STYLES, (
        "knowledge-guide-toggle must exist as a button class in styles.css"
    )
    block = _css_block(STYLES, ".knowledge-guide-toggle {")
    assert "grid-template-columns: 1fr auto" in block, (
        "knowledge-guide-toggle must use 1fr auto grid"
    )


def test_guide_toggle_collapses_inner_padding_when_collapsed() -> None:
    """The guide card's outer chrome (border / box-shadow / radius) must
    stay in place when collapsed — only the inner padding collapses via
    the toggle button's padding. The body wrapper is `hidden` and
    contributes nothing visually."""
    # Card chrome stays
    block = _css_block(STYLES, ".knowledge-guide-card {")
    assert "linear-gradient(180deg, rgba(255, 253, 249, 0.92)" in block, (
        "knowledge-guide-card outer gradient must remain so the chrome "
        "(border / box-shadow) stays consistent across open / closed"
    )
    assert "border-radius: 12px" in block, (
        "guide card must keep its rounded corners when collapsed — "
        "the button alone shrinks the inner padding, not the chrome"
    )
    # Toggle button padding defines inner padding
    toggle_block = _css_block(STYLES, ".knowledge-guide-toggle {")
    assert "padding: 18px 24px" in toggle_block, (
        "guide toggle button padding defines the inner padding of "
        "the collapsed-state card"
    )


def test_section_toggle_focus_visible_uses_accent_outline() -> None:
    """Keyboard navigation must surface a visible focus ring on both
    section and guide toggles — the user is going to tab through 20+
    sections, so the outline can't be invisible."""
    assert (
        ".disclosure-toggle:focus-visible"
        in EDITORIAL
    )
    assert (
        'outline: 2px solid var(--accent-strong)' in EDITORIAL
    ), "section toggle focus-visible must use --accent-strong outline"
    assert (
        ".knowledge-guide-toggle:focus-visible" in STYLES
    ), "guide toggle must also define a :focus-visible state"


def test_chevron_icon_is_svg_with_rotation_transition() -> None:
    """The shared chevron owns SVG sizing and the rotation transition."""
    assert ".disclosure-toggle__chevron svg {" in EDITORIAL
    block = _css_block(EDITORIAL, ".disclosure-toggle__chevron svg {")
    assert "transition: transform var(--dur-hover) var(--ease-out)" in block
