import type { ShortageOrder } from "../lib/types";

type ShortageTableProps = {
  orders: ShortageOrder[];
  expandedOrders: Record<string, boolean>;
  expandedKits: Record<string, boolean>;
  onToggleOrder: (orderId: string) => void;
  onToggleKit: (kitId: string) => void;
};

const numberFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

export const ShortageTable = ({
  orders,
  expandedOrders,
  expandedKits,
  onToggleOrder,
  onToggleKit
}: ShortageTableProps) => (
  <table className="shortage-table">
    <thead>
      <tr>
        <th>Document Number | Item</th>
        <th>Customer</th>
        <th>Service</th>
        <th>Aux Ship Date</th>
        <th>Ordered</th>
        <th>On Hand</th>
        <th>Remaining (OH-Ord)</th>
      </tr>
    </thead>
    <tbody>
      {orders.map((order) => (
        <>
          <tr key={`header-${order.soNum}`} className="parent-row" onClick={() => onToggleOrder(order.soNum)}>
            <td colSpan={2}>
              <span className="toggle-icon">{expandedOrders[order.soNum] ? "[-]" : "[+]"}</span>
              {order.soNum}
            </td>
            <td>{order.serviceType || "-"}</td>
            <td />
            <td>{numberFormat.format(order.totalOrdered)}</td>
            <td colSpan={2} />
          </tr>
          {expandedOrders[order.soNum] &&
            order.lines.map((line) => {
              if (line.isKit) {
                const kitId = `${order.soNum}-${line.itemId}`;
                return (
                  <>
                    <tr
                      key={`kit-${kitId}`}
                      className="shortage-row kit-row"
                      onClick={() => onToggleKit(kitId)}
                    >
                      <td className="indent-1">
                        <span className="toggle-icon">{expandedKits[kitId] ? "[-]" : "[+]"}</span>
                        <strong>{line.itemName}</strong>
                      </td>
                      <td>{order.customer}</td>
                      <td>{order.serviceType || "-"}</td>
                      <td>{line.date || "-"}</td>
                      <td>{numberFormat.format(line.orderedQty)}</td>
                      <td>-</td>
                      <td>-</td>
                    </tr>
                    {expandedKits[kitId] &&
                      line.components.map((component) => (
                        <tr key={`kit-comp-${kitId}-${component.itemId}`} className="shortage-row">
                          <td className="indent-2">↳ {component.itemName}</td>
                          <td />
                          <td />
                          <td />
                          <td>{numberFormat.format(component.orderedQty)}</td>
                          <td>{numberFormat.format(component.onHandQty)}</td>
                          <td>{numberFormat.format(component.remainingStock)}</td>
                        </tr>
                      ))}
                  </>
                );
              }
              return (
                <tr key={`line-${order.soNum}-${line.itemId}`} className="shortage-row">
                  <td className="indent-1">{line.itemName}</td>
                  <td>{order.customer}</td>
                  <td>{order.serviceType || "-"}</td>
                  <td>{line.date || "-"}</td>
                  <td>{numberFormat.format(line.orderedQty)}</td>
                  <td>{numberFormat.format(line.onHandQty ?? 0)}</td>
                  <td>{numberFormat.format(line.remainingStock ?? 0)}</td>
                </tr>
              );
            })}
        </>
      ))}
    </tbody>
  </table>
);
