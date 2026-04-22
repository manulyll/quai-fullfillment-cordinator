import { useMemo, useState } from "react";
import type { CSSProperties } from "react";
import type { ShortageOrder } from "../lib/types";

type ShipCalendarProps = {
  orders: ShortageOrder[];
  initialDate: string;
};

type DayBucket = {
  dateKey: string;
  orders: ShortageOrder[];
};

const monthLabel = (date: Date): string =>
  date.toLocaleString(undefined, { month: "long", year: "numeric", timeZone: "UTC" });

const dateKey = (value: Date): string => value.toISOString().slice(0, 10);

const startOfMonth = (value: Date): Date => new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), 1));

const buildGrid = (month: Date): Date[] => {
  const start = startOfMonth(month);
  const offset = start.getUTCDay();
  const gridStart = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate() - offset));
  return Array.from({ length: 42 }, (_, index) => {
    const day = new Date(gridStart);
    day.setUTCDate(gridStart.getUTCDate() + index);
    return day;
  });
};

const statusClassName = (status: string): string => {
  const normalized = status.toLowerCase();
  if (normalized.includes("closed") || normalized.includes("billed")) {
    return "calendar-chip status-confirmed";
  }
  if (normalized.includes("pending billing/partially fulfilled") || normalized.includes("partial")) {
    return "calendar-chip status-partial";
  }
  if (normalized.includes("pending fulfillment") || normalized.includes("pending billing")) {
    return "calendar-chip status-pending";
  }
  return "calendar-chip status-unknown";
};

const statusChipStyle = (status: string): CSSProperties => {
  const normalized = status.toLowerCase();
  if (normalized.includes("closed") || normalized.includes("billed") || normalized.includes("confirm")) {
    return { backgroundColor: "#d1fae5", borderColor: "#10b981", color: "#065f46", borderLeft: "4px solid #10b981" };
  }
  if (normalized.includes("tentative")) {
    return { backgroundColor: "#efe3ff", borderColor: "#a855f7", color: "#581c87", borderLeft: "4px solid #a855f7" };
  }
  if (normalized.includes("pending billing/partially fulfilled") || normalized.includes("partial")) {
    return { backgroundColor: "#fee2e2", borderColor: "#ef4444", color: "#7f1d1d", borderLeft: "4px solid #ef4444" };
  }
  if (normalized.includes("pending fulfillment") || normalized.includes("pending billing")) {
    return { backgroundColor: "#fef3c7", borderColor: "#f59e0b", color: "#78350f", borderLeft: "4px solid #f59e0b" };
  }
  return { backgroundColor: "#dbeafe", borderColor: "#3b82f6", color: "#1e3a8a", borderLeft: "4px solid #3b82f6" };
};

export const ShipCalendar = ({ orders, initialDate }: ShipCalendarProps) => {
  const initial = initialDate ? new Date(`${initialDate}T00:00:00Z`) : new Date();
  const [activeMonth, setActiveMonth] = useState(startOfMonth(initial));

  const ordersByDate = useMemo(() => {
    const map = new Map<string, DayBucket>();
    orders.forEach((order) => {
      if (!order.date) {
        return;
      }
      const key = order.date;
      const existing = map.get(key);
      if (existing) {
        existing.orders.push(order);
      } else {
        map.set(key, { dateKey: key, orders: [order] });
      }
    });
    return map;
  }, [orders]);

  const days = useMemo(() => buildGrid(activeMonth), [activeMonth]);
  const activeMonthIndex = activeMonth.getUTCMonth();

  return (
    <section className="calendar-wrap">
      <div className="calendar-toolbar">
        <button
          onClick={() =>
            setActiveMonth((current) => new Date(Date.UTC(current.getUTCFullYear(), current.getUTCMonth() - 1, 1)))
          }
        >
          Prev
        </button>
        <h3>{monthLabel(activeMonth)}</h3>
        <button
          onClick={() =>
            setActiveMonth((current) => new Date(Date.UTC(current.getUTCFullYear(), current.getUTCMonth() + 1, 1)))
          }
        >
          Next
        </button>
      </div>
      <div className="calendar-legend">
        <span className="legend-pill legend-confirmed">Confirmed / Closed / Billed</span>
        <span className="legend-pill legend-tentative">Tentative</span>
        <span className="legend-pill legend-pending">Pending Fulfillment / Billing</span>
        <span className="legend-pill legend-partial">Partially Fulfilled</span>
        <span className="legend-pill legend-unknown">Other</span>
      </div>

      <div className="calendar-grid">
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((name) => (
          <div key={name} className="calendar-weekday">
            {name}
          </div>
        ))}
        {days.map((day) => {
          const key = dateKey(day);
          const bucket = ordersByDate.get(key);
          const inActiveMonth = day.getUTCMonth() === activeMonthIndex;
          return (
            <div key={key} className={`calendar-day${inActiveMonth ? "" : " muted"}`}>
              <div className="calendar-day-head">{day.getUTCDate()}</div>
              <div className="calendar-day-list">
                {(bucket?.orders ?? []).slice(0, 3).map((order) => (
                  <a
                    key={`${key}-${order.soNum}`}
                    className={statusClassName(order.status || "")}
                    style={statusChipStyle(order.status || "")}
                    href={`/api/shortages/picking-ticket/${encodeURIComponent(order.soNum)}`}
                    target="_blank"
                    rel="noreferrer"
                    title={`Open picking ticket for ${order.soNum}`}
                  >
                    {order.soNum} | {order.city || order.customer} | {order.serviceType || "-"} | {order.status || "-"}
                  </a>
                ))}
                {(bucket?.orders.length ?? 0) > 3 && (
                  <div className="calendar-more">+{(bucket?.orders.length ?? 0) - 3} more</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};
