import type { ShortageOrder } from "../lib/types";

type ItemGroupedTableProps = {
  orders: ShortageOrder[];
};

type ItemSummary = {
  itemId: number;
  itemName: string;
  soNums: Set<string>;
  requiredQty: number;
  onHandQty: number;
  shortageQty: number;
};

const numberFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

const upsert = (map: Map<number, ItemSummary>, itemId: number, itemName: string): ItemSummary => {
  const current = map.get(itemId);
  if (current) {
    return current;
  }
  const created: ItemSummary = {
    itemId,
    itemName,
    soNums: new Set<string>(),
    requiredQty: 0,
    onHandQty: 0,
    shortageQty: 0
  };
  map.set(itemId, created);
  return created;
};

const summarizeByItem = (orders: ShortageOrder[]): ItemSummary[] => {
  const byItem = new Map<number, ItemSummary>();

  orders.forEach((order) => {
    order.lines.forEach((line) => {
      if (line.isKit) {
        line.components.forEach((component) => {
          const summary = upsert(byItem, component.itemId, component.itemName);
          summary.soNums.add(order.soNum);
          summary.requiredQty += component.orderedQty;
          summary.onHandQty += component.onHandQty;
          summary.shortageQty += Math.max(0, component.orderedQty - component.onHandQty);
        });
        return;
      }

      const onHand = line.onHandQty ?? 0;
      const summary = upsert(byItem, line.itemId, line.itemName);
      summary.soNums.add(order.soNum);
      summary.requiredQty += line.orderedQty;
      summary.onHandQty += onHand;
      summary.shortageQty += Math.max(0, line.orderedQty - onHand);
    });
  });

  return Array.from(byItem.values()).sort((a, b) => b.shortageQty - a.shortageQty);
};

export const ItemGroupedTable = ({ orders }: ItemGroupedTableProps) => {
  const items = summarizeByItem(orders);

  if (items.length === 0) {
    return <div className="state-box">No grouped item shortages found for this range.</div>;
  }

  return (
    <table className="shortage-table">
      <thead>
        <tr>
          <th>Item</th>
          <th>Shortage Qty</th>
          <th>Required Qty</th>
          <th>On Hand Qty</th>
          <th>Sales Orders</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.itemId} className="shortage-row">
            <td>{item.itemName}</td>
            <td>{numberFormat.format(item.shortageQty)}</td>
            <td>{numberFormat.format(item.requiredQty)}</td>
            <td>{numberFormat.format(item.onHandQty)}</td>
            <td>{Array.from(item.soNums).slice(0, 10).join(", ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
