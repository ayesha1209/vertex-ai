import { useEffect, useRef } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import TextAlign from "@tiptap/extension-text-align";
import Table from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import { generateJSON } from "@tiptap/html";
import { TermsSigWrapper } from "./TermsSigWrapper";
import { recalcQuotationTotals } from "../../lib/recalcQuotationTotals";

const RECALC_DEBOUNCE_MS = 500;

interface Props {
  initialHtml: string | null;
  onChange: (html: string) => void;
}

export function VertexEditor({ initialHtml, onChange }: Props) {
  const recalcTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Underline,
      Link.configure({ openOnClick: false }),
      TextAlign.configure({
        types: ["heading", "paragraph"]
      }),
      Table.configure({
        resizable: true
      }),
      TableRow,
      TableHeader,
      TableCell,
      TermsSigWrapper
    ],
    content: "",
    onUpdate({ editor: ed }) {
      const html = ed.getHTML();
      onChange(html);

      if (recalcTimeoutRef.current) clearTimeout(recalcTimeoutRef.current);
      recalcTimeoutRef.current = setTimeout(() => {
        recalcTimeoutRef.current = null;
        const current = ed.getHTML();
        const updated = recalcQuotationTotals(current);
        if (updated !== current) {
          const windowScrollY = typeof window !== "undefined" ? window.scrollY : 0;
          let scrollable: Element | null = ed.view.dom.parentElement;
          let savedScrollTop: number | null = null;
          while (scrollable) {
            if (scrollable.scrollHeight > scrollable.clientHeight) {
              savedScrollTop = scrollable.scrollTop;
              break;
            }
            scrollable = scrollable.parentElement;
          }
          ed.commands.setContent(updated, false);
          onChange(updated);
          requestAnimationFrame(() => {
            if (typeof window !== "undefined") window.scrollTo(window.scrollX, windowScrollY);
            if (scrollable && savedScrollTop !== null) scrollable.scrollTop = savedScrollTop;
          });
        }
      }, RECALC_DEBOUNCE_MS);
    }
  });

  const didInit = useRef(false);
  useEffect(() => {
    if (editor && initialHtml && !didInit.current) {
      didInit.current = true;
      console.log("[VertexEditor] initializing content, length:", initialHtml.length);
      try {
        const json = generateJSON(initialHtml, editor.extensionManager.extensions);
        editor.commands.setContent(json, false);
      } catch {
        editor.commands.setContent(initialHtml, false);
      }
      // Notify parent of the actual rendered HTML so currentHtml is never stale
      requestAnimationFrame(() => {
        const renderedHtml = editor.getHTML();
        console.log("[VertexEditor] post-init HTML length:", renderedHtml.length);
        onChange(renderedHtml);
      });
    }
  }, [editor, initialHtml, onChange]);

  useEffect(() => {
    return () => {
      if (recalcTimeoutRef.current) clearTimeout(recalcTimeoutRef.current);
    };
  }, []);

  if (!editor) return null;

  const toggle = (action: () => void, isActive: boolean) => {
    action();
    return isActive;
  };

  return (
    <div className="vertex-editor">
      <div className="mb-3 flex flex-wrap items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-xs">
        <button
          type="button"
          className={`btn h-7 px-2 text-[11px] ${
            editor.isActive("bold") ? "bg-sky-600 text-white" : "bg-white border border-slate-200 text-slate-700"
          }`}
          onClick={() =>
            toggle(() => editor.chain().focus().toggleBold().run(), editor.isActive("bold"))
          }
        >
          B
        </button>
        <button
          type="button"
          className={`btn h-7 px-2 text-[11px] ${
            editor.isActive("italic") ? "bg-sky-600 text-white" : "bg-white border border-slate-200 text-slate-700"
          }`}
          onClick={() =>
            toggle(
              () => editor.chain().focus().toggleItalic().run(),
              editor.isActive("italic")
            )
          }
        >
          I
        </button>
        <button
          type="button"
          className={`btn h-7 px-2 text-[11px] ${
            editor.isActive("underline") ? "bg-sky-600 text-white" : "bg-white border border-slate-200 text-slate-700"
          }`}
          onClick={() =>
            toggle(
              () => editor.chain().focus().toggleUnderline().run(),
              editor.isActive("underline")
            )
          }
        >
          U
        </button>
        <span className="mx-1 h-4 w-px bg-slate-200" />
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().setTextAlign("left").run()}
        >
          Left
        </button>
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().setTextAlign("center").run()}
        >
          Center
        </button>
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().setTextAlign("right").run()}
        >
          Right
        </button>
        <span className="mx-1 h-4 w-px bg-slate-200" />
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().toggleBulletList().run()}
        >
          Bullets
        </button>
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
        >
          Numbered
        </button>
        <span className="mx-1 h-4 w-px bg-slate-200" />
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3 }).run()}
        >
          Insert table
        </button>
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().addRowAfter().run()}
        >
          Row +
        </button>
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().addRowBefore().run()}
        >
          Row ^
        </button>
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().deleteRow().run()}
        >
          Row -
        </button>
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().addColumnAfter().run()}
        >
          Col +
        </button>
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().addColumnBefore().run()}
        >
          Col &lt;
        </button>
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().deleteColumn().run()}
        >
          Col -
        </button>
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().mergeCells().run()}
        >
          Merge
        </button>
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().splitCell().run()}
        >
          Split
        </button>
        <span className="mx-1 h-4 w-px bg-slate-200" />
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().undo().run()}
        >
          Undo
        </button>
        <button
          type="button"
          className="btn h-7 px-2 text-[11px]"
          onClick={() => editor.chain().focus().redo().run()}
        >
          Redo
        </button>
      </div>
      <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}

