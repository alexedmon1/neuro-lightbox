"""Digests: a short, scannable summary of an analysis's results, by contrast.

A profile turns an analysis's tables into a digest (its builders know the
columns); this module is what every digest shares: the sections a study's
contrast tiers make, an in-place item for each contrast that was run without a
significant result, and the role badge (confirmatory / exploratory, gated on …)
each contrast carries.
"""

from __future__ import annotations

from html import escape


def build_digest(build, tables: list[dict], contrast_labels: dict | None = None,
                 contrast_groups: dict | None = None, contrast_meta: dict | None = None,
                 **kwargs) -> str | None:
    """``build(tables, contrast_labels, contrast_groups, **kwargs)``'s HTML, with
    each contrast badged with its role from ``contrast_meta`` ({role, test, gate_on}).
    """
    html = build(tables, contrast_labels, contrast_groups, **kwargs)
    if html is None or not contrast_meta:
        return html
    return _apply_role_badges(html, contrast_labels or {}, contrast_meta)


def _apply_role_badges(html: str, labels: dict, contrast_meta: dict) -> str:
    """Append a role badge (confirmatory / exploratory; gated-on note) after each
    contrast's name span. Every digest builder emits the same
    ``<span class="sig-contrast">label</span>`` fragment, so one pass covers all
    of them without threading the metadata through each builder.
    """
    for name, meta in contrast_meta.items():
        if not isinstance(meta, dict):
            continue
        role = meta.get("role")
        gate = meta.get("gate_on") or []
        if isinstance(gate, str):
            gate = [gate]
        if not role and not gate:
            continue
        badge = ""
        if role:
            badge += f'<span class="sig-role sig-role-{escape(str(role))}">{escape(str(role))}</span>'
        if gate:
            gate_labels = ", ".join(str(labels.get(g, g)) for g in gate)
            badge += (f'<span class="sig-gate" title="Only interpreted if the gating '
                      f'contrast is significant">gated on {escape(gate_labels)}</span>')
        frag = f'<span class="sig-contrast">{escape(str(labels.get(name, name)))}</span>'
        html = html.replace(frag, frag + badge)
    return html


def _null_item(label, note: str) -> str:
    """A list item for a comparison that was run but had no significant result —
    shown in place, so it's clear the test was done."""
    return (f'<li class="sig-null-item"><span class="sig-contrast">{escape(str(label))}</span> '
            f'<span class="sig-none-inline">{note}</span></li>')


def _fill_nulls(all_contrasts, item_by_contrast, _label, note: str) -> None:
    """Add an in-place 'no significant …' item for every contrast without one."""
    for c in all_contrasts:
        if c not in item_by_contrast:
            item_by_contrast[c] = _null_item(_label(c), note)


def _render_body(all_contrasts, item_by_contrast, groups: dict) -> str:
    """Shared body renderer: tier sections (YAML order) when groups given, else flat."""
    def _ul(contrasts):
        return '<ul class="sig-list">' + "".join(item_by_contrast[c] for c in contrasts) + "</ul>"

    if not groups:
        return _ul([c for c in all_contrasts if c in item_by_contrast])

    group_order = []
    for g in groups.values():
        if g and g not in group_order:
            group_order.append(g)
    body = ""
    rendered = set()
    for grp in group_order:
        members = [c for c in all_contrasts if c in item_by_contrast and groups.get(c) == grp]
        if not members:
            continue
        body += '<h4 class="sig-group">' + escape(grp) + "</h4>" + _ul(members)
        rendered.update(members)
    leftover = [c for c in all_contrasts if c in item_by_contrast and c not in rendered]
    if leftover:
        body += '<h4 class="sig-group">Other</h4>' + _ul(leftover)
    return body
