import { Node, mergeAttributes } from "@tiptap/core";

/**
 * Preserves wrapper divs (identified by class) that TipTap would otherwise
 * silently unwrap on load+save. The print CSS keys font sizing and section
 * styling off .coa-section (COA) and .engineering-tech-doc (engineering
 * TDS), so losing them after an edit makes a previously-edited document
 * render with different type sizes. .quotation-page matters specifically on
 * the xhtml2pdf fallback rendering path (used when WeasyPrint is
 * unavailable) — WeasyPrint always re-wraps its own fresh quotation-page
 * div regardless, but xhtml2pdf does not, so a stripped wrapper there loses
 * the tighter one-page spacing rules. .invoice-family-page has no print CSS
 * of its own yet, but is included so a future rule added for it doesn't
 * silently break the same way. Same fix pattern as TermsSigWrapper.ts,
 * generalized to an allow-list of classes so new ones can be added in one
 * place instead of writing a new dedicated Node each time.
 */
const PRESERVED_CLASSES = [
  "coa-section",
  "engineering-tech-doc",
  "quotation-page",
  "invoice-family-page",
];

export const PreservedSectionDiv = Node.create({
  name: "preservedSectionDiv",

  group: "block",
  content: "block+",

  parseHTML() {
    return [
      {
        tag: "div",
        getAttrs: (dom) => {
          const el = dom as HTMLElement;
          const cls = el.getAttribute("class") || "";
          if (PRESERVED_CLASSES.some((preserved) => cls.includes(preserved))) {
            return { class: cls };
          }
          return false;
        },
      },
    ];
  },

  addAttributes() {
    return {
      class: {
        default: "",
        parseHTML: (element) => (element as HTMLElement).getAttribute("class") || "",
        renderHTML: (attributes) => (attributes.class ? { class: attributes.class } : {}),
      },
    };
  },

  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes), 0];
  },
});
