/**
 * Recalculate quotation line amounts (Quantity × Unit Price) and Total Amount
 * from document HTML. Returns modified HTML if changes were made.
 */

function parseNumber(text: string): number {
  if (!text || !String(text).trim()) return 0;
  const cleaned = String(text)
    .replace(/[₹$,\s]/g, "")
    .replace(/[\u20B9]/g, ""); // rupee
  const n = parseFloat(cleaned);
  return Number.isFinite(n) ? n : 0;
}

function extractQuantity(text: string): number {
  // "50 MT" -> 50, "100" -> 100
  const m = String(text).trim().match(/^[\d.,]+/);
  if (m) return parseNumber(m[0]);
  return parseNumber(text);
}

function getCurrencySymbol(html: string): string {
  if (/₹|Rs\.|INR|Rupee/i.test(html)) return "₹";
  return "$";
}

function formatAmount(value: number, currency: string): string {
  const formatted = value.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return currency === "₹" ? `₹${formatted}` : `$${formatted}`;
}

export function recalcQuotationTotals(html: string): string {
  if (!html || typeof document === "undefined") return html;

  const parser = new DOMParser();
  const doc = parser.parseFromString(`<div id="__recalc">${html}</div>`, "text/html");
  const root = doc.getElementById("__recalc");
  if (!root) return html;

  const tables = root.querySelectorAll("table");
  let itemsTable: HTMLTableElement | null = null;
  let totalsTable: HTMLTableElement | null = null;

  for (const table of tables) {
    const firstRow = table.querySelector("tr");
    if (!firstRow) continue;
    const cells = firstRow.querySelectorAll("td, th");
    const firstCellText = (cells[0]?.textContent || "").toLowerCase();
    const allText = Array.from(cells)
      .map((c) => (c?.textContent || "").toLowerCase())
      .join(" ");
    if (
      (allText.includes("quantity") && allText.includes("unit price") && allText.includes("amount")) ||
      table.classList.contains("items-table")
    ) {
      itemsTable = table as HTMLTableElement;
    }
    if (firstCellText.includes("total amount") || table.classList.contains("totals-table")) {
      totalsTable = table as HTMLTableElement;
    }
  }

  if (!itemsTable) return html;

  const rows = itemsTable.querySelectorAll("tr");
  if (rows.length < 2) return html;

  const currency = getCurrencySymbol(html);
  let total = 0;
  let changed = false;

  // Skip header (index 0); data rows from index 1
  for (let r = 1; r < rows.length; r++) {
    const row = rows[r];
    const tds = row.querySelectorAll("td");
    if (tds.length < 5) continue;

    const qtyText = tds[2]?.textContent?.trim() ?? "";
    const priceText = tds[3]?.textContent?.trim() ?? "";
    const qty = extractQuantity(qtyText);
    const price = parseNumber(priceText);
    const amount = qty * price;
    total += amount;

    const newAmountStr = formatAmount(amount, currency);
    const currentAmount = (tds[4]?.textContent || "").trim();
    const currentNormalized = parseNumber(currentAmount).toFixed(2);
    const newNormalized = amount.toFixed(2);
    if (currentNormalized !== newNormalized && tds[4]) {
      tds[4].innerHTML = newAmountStr;
      changed = true;
    }
  }

  if (totalsTable) {
    const totalRows = totalsTable.querySelectorAll("tr");
    for (const row of totalRows) {
      const tds = row.querySelectorAll("td");
      const label = (tds[0]?.textContent || "").trim().toLowerCase();
      if (label.includes("total amount") && tds[1]) {
        const newTotalStr = formatAmount(total, currency);
        if ((tds[1].textContent || "").trim() !== newTotalStr) {
          tds[1].innerHTML = newTotalStr;
          changed = true;
        }
        break;
      }
    }
  }

  if (!changed) return html;

  return root.innerHTML;
}
