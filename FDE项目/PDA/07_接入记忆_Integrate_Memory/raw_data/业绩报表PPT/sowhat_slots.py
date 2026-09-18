"""
sowhat_slots.py — discover every 'So What' label in the deck and map it to
its content shape. Used by final_gap_patch to update each So What with a
fresh data-driven blurb.

Returns a list of records:
  { 'slide': int (0-based),
    'label':  Shape ref  (the shape whose text starts with 'So What'),
    'content': Shape ref (where the descriptive text lives; may == label if merged),
    'type':   'MERGED' | 'SEPARATE' }
"""


def find_sowhat_slots(prs):
    slots = []
    for si, s in enumerate(prs.slides):
        labels = [sh for sh in s.shapes
                  if sh.has_text_frame and sh.text_frame.text.strip().startswith('So What')]

        # Find all plausible "content" shapes on this slide
        content_pool = []
        for sh in s.shapes:
            if not sh.has_text_frame:
                continue
            t = sh.text_frame.text.strip()
            if len(t) < 40 or t.startswith('So What'):
                continue
            content_pool.append(sh)

        # For each label, pick the content shape that
        #   (a) starts at/below the label (cy in [ly-20k, ly+400k])
        #   (b) has x center closest to label x center, OR its horizontal span contains label
        # Already-assigned content shapes are removed from the pool so two
        # labels can't grab the same content.
        assigned = set()
        for sl in labels:
            rest = sl.text_frame.text.strip().replace('So What：', '', 1).strip()
            if len(rest) > 20:
                slots.append({'slide': si, 'label': sl, 'content': sl, 'type': 'MERGED'})
                continue

            lcx = sl.left + (sl.width or 0) // 2
            ly = sl.top

            best = None
            best_score = None
            for sh in content_pool:
                if id(sh) in assigned:
                    continue
                cy = sh.top
                if cy < ly - 20000 or cy > ly + 400000:
                    continue
                cx = sh.left + (sh.width or 0) // 2
                left_edge = sh.left
                right_edge = sh.left + (sh.width or 0)
                contains = left_edge <= lcx <= right_edge
                if not contains and abs(cx - lcx) > 3_000_000:
                    continue
                # score: closest y first, then containment bonus, then x dist
                score = (cy - ly) * 5
                if not contains:
                    score += abs(cx - lcx)
                if best_score is None or score < best_score:
                    best = sh
                    best_score = score

            if best is not None:
                slots.append({'slide': si, 'label': sl, 'content': best, 'type': 'SEPARATE'})
                assigned.add(id(best))
            else:
                slots.append({'slide': si, 'label': sl, 'content': None, 'type': 'ORPHAN'})

    return slots


if __name__ == "__main__":
    from pptx import Presentation
    import sys
    prs = Presentation(sys.argv[1] if len(sys.argv) > 1
                       else "周业绩汇报PPT_FINAL.pptx")
    slots = find_sowhat_slots(prs)
    print(f"Found {len(slots)} slots")
    from collections import Counter
    print(Counter(s['type'] for s in slots))
    for s in slots:
        t = (s['content'].text_frame.text.strip()[:50]
             if s['content'] and s['content'] is not s['label']
             else s['label'].text_frame.text.strip().replace('So What：','')[:50])
        print(f"  Slide {s['slide']+1}  label_y={s['label'].top:>8}  "
              f"label_x={s['label'].left:>8}  [{s['type']}]  {t!r}")
