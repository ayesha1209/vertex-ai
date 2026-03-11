import { Node, mergeAttributes } from "@tiptap/core";

/**
 * Preserves the terms-and-signatory wrapper div when loading/saving document HTML.
 * Without this, TipTap's default schema strips unknown divs and the terms block
 * structure is lost after edit + save, breaking PDF layout.
 */
export const TermsSigWrapper = Node.create({
  name: "termsSigWrapper",

  group: "block",
  content: "block+",

  parseHTML() {
    return [
      {
        tag: "div",
        getAttrs: (dom) => {
          const el = dom as HTMLElement;
          const cls = el.getAttribute("class") || "";
          if (cls.includes("terms-sig-wrapper")) {
            return {
              class: cls,
              style: el.getAttribute("style") || undefined,
            };
          }
          return false;
        },
      },
    ];
  },

  addAttributes() {
    return {
      class: {
        default: "terms-sig-wrapper",
        parseHTML: (el) => (el as HTMLElement).getAttribute("class") || "terms-sig-wrapper",
        renderHTML: (attrs) => (attrs.class ? { class: attrs.class } : {}),
      },
      style: {
        default: "page-break-before:avoid !important; margin-top:0; padding-top:0;",
        parseHTML: (el) =>
          (el as HTMLElement).getAttribute("style") ||
          "page-break-before:avoid !important; margin-top:0; padding-top:0;",
        renderHTML: (attrs) => (attrs.style ? { style: attrs.style } : {}),
      },
    };
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(
        {
          class: "terms-sig-wrapper",
          style:
            "page-break-before:avoid !important; margin-top:0; padding-top:0;",
        },
        HTMLAttributes
      ),
      0,
    ];
  },
});
