import { FormEvent, useEffect, useMemo, useState } from "react";
import { ItemGroupedTable } from "../components/ItemGroupedTable";
import { ShipCalendar } from "../components/ShipCalendar";
import { ShortageTable } from "../components/ShortageTable";
import { apiClient } from "../lib/api";
import type {
  LocationOption,
  NextDayOrdersResponse,
  ShortageReportResponse,
  UserInfo
} from "../lib/types";

type ShortagePageProps = {
  token: string;
  onLogout: () => void;
};

const isoDate = (value: Date): string => value.toISOString().slice(0, 10);

const defaultDateRange = (): { startDate: string; endDate: string } => {
  const now = new Date();
  const day = now.getUTCDay();
  let daysUntilStart = 14 - day;
  if (day === 0) {
    daysUntilStart = 14;
  }
  const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + daysUntilStart));
  const end = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate() + 14));
  return { startDate: isoDate(start), endDate: isoDate(end) };
};

export const ShortagePage = ({ token, onLogout }: ShortagePageProps) => {
  type ViewMode = "order" | "item" | "calendar" | "daily";
  const logoSrc = "/logo.jpg?v=20260415";
  const defaults = useMemo(defaultDateRange, []);
  const [me, setMe] = useState<UserInfo | null>(null);
  const [locations, setLocations] = useState<LocationOption[]>([]);
  const [report, setReport] = useState<ShortageReportResponse | null>(null);
  const [nextDay, setNextDay] = useState<NextDayOrdersResponse | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("order");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [locationId, setLocationId] = useState<string>("");
  const [startDate, setStartDate] = useState(defaults.startDate);
  const [endDate, setEndDate] = useState(defaults.endDate);
  const [expandedOrders, setExpandedOrders] = useState<Record<string, boolean>>({});
  const [expandedKits, setExpandedKits] = useState<Record<string, boolean>>({});
  const [dailyChecklist, setDailyChecklist] = useState<Record<string, boolean>>(() => {
    try {
      const raw = localStorage.getItem("quai-daily-checklist");
      return raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
    } catch {
      return {};
    }
  });

  const loadReport = async (nextFilters?: { locationId?: number; startDate?: string; endDate?: string }) => {
    setLoading(true);
    setError(null);
    try {
      const filters = nextFilters ?? {
        locationId: locationId ? Number(locationId) : undefined,
        startDate,
        endDate
      };
      const user = await apiClient.getMe(token);
      setMe(user);
      const [locationsPayload, reportPayload, nextDayPayload] = await Promise.all([
        apiClient.getLocations(token),
        apiClient.getShortages(token, filters),
        apiClient.getNextDayOrders(token)
      ]);
      setLocations(locationsPayload.locations);
      setReport(reportPayload);
      setNextDay(nextDayPayload);
      setExpandedOrders(
        reportPayload.orders.reduce<Record<string, boolean>>((acc, order) => {
          acc[order.soNum] = true;
          return acc;
        }, {})
      );
      setExpandedKits({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load shortage report");
    } finally {
      setLoading(false);
    }
  };

  const toggleChecklist = (key: string) => {
    setDailyChecklist((current) => {
      const updated = { ...current, [key]: !current[key] };
      localStorage.setItem("quai-daily-checklist", JSON.stringify(updated));
      return updated;
    });
  };

  useEffect(() => {
    void loadReport({
      startDate: defaults.startDate,
      endDate: defaults.endDate
    });
  }, [defaults.endDate, defaults.startDate]);

  const onFilterSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await loadReport({
      locationId: locationId ? Number(locationId) : undefined,
      startDate,
      endDate
    });
  };

  return (
    <main className="dashboard-page">
      <header className="topbar">
        <div className="navbar-title">
          <img
            src={logoSrc}
            alt="Quai"
            className="navbar-brand-logo"
            onError={(event) => {
              event.currentTarget.src = "/logo.svg";
            }}
          />
        </div>
        <div>
          <h1>2-Week Detailed Shortage Report</h1>
          <p>
            User: {me?.username ?? "Loading user..."} | Roles: {me?.roles?.join(", ") ?? "none"}
          </p>
        </div>
        <div className="topbar-actions">
          <button onClick={() => void loadReport()} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
          <button onClick={onLogout}>Sign out</button>
        </div>
      </header>

      <section className="card">
        <form className="shortage-filters" onSubmit={onFilterSubmit}>
          <label>
            Location
            <select value={locationId} onChange={(event) => setLocationId(event.target.value)}>
              <option value="">All locations</option>
              {locations.map((location) => (
                <option key={location.id} value={location.id}>
                  {location.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Start Date
            <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required />
          </label>
          <label>
            End Date
            <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} required />
          </label>
          <button type="submit" disabled={loading}>
            Refresh Report
          </button>
        </form>
      </section>
      <div className="status-banner">Data source: NetSuite SuiteQL (live).</div>
      <section className="view-tabs">
        <button
          className={viewMode === "order" ? "active" : ""}
          onClick={() => setViewMode("order")}
          type="button"
        >
          Grouped by Sales Order
        </button>
        <button
          className={viewMode === "item" ? "active" : ""}
          onClick={() => setViewMode("item")}
          type="button"
        >
          Grouped by Item
        </button>
        <button
          className={viewMode === "calendar" ? "active" : ""}
          onClick={() => setViewMode("calendar")}
          type="button"
        >
          Ship Calendar
        </button>
        <button
          className={viewMode === "daily" ? "active" : ""}
          onClick={() => setViewMode("daily")}
          type="button"
        >
          Daily Coordinator
        </button>
      </section>

      {loading && <div className="state-box">Loading shortage report...</div>}
      {error && !loading && <div className="error-box">{error}</div>}

      {!loading && !error && report && (
        <>
          <section className="meta-row">
            <span>Orders with shortages: {report.totalOrders}</span>
            <span>Start: {report.startDate}</span>
            <span>End: {report.endDate}</span>
            <span>As of: {new Date(report.asOf).toLocaleString()}</span>
          </section>

          {report.orders.length === 0 && viewMode !== "daily" ? (
            <section className="card">
              <div className="state-box">No shortages found for the selected filters.</div>
            </section>
          ) : (
            <section className="card">
              {viewMode === "order" && (
                <ShortageTable
                  orders={report.orders}
                  expandedOrders={expandedOrders}
                  expandedKits={expandedKits}
                  onToggleOrder={(orderId) =>
                    setExpandedOrders((current) => ({ ...current, [orderId]: !current[orderId] }))
                  }
                  onToggleKit={(kitId) =>
                    setExpandedKits((current) => ({ ...current, [kitId]: !current[kitId] }))
                  }
                />
              )}
              {viewMode === "item" && <ItemGroupedTable orders={report.orders} />}
              {viewMode === "calendar" && (
                <ShipCalendar orders={report.orders} initialDate={report.startDate} />
              )}
              {viewMode === "daily" && (
                <section className="daily-board">
                  <div className="state-box">
                    Next-day date: {nextDay?.date ?? "-"} | Total orders: {nextDay?.totalOrders ?? 0} | Unconfirmed:{" "}
                    {nextDay?.unconfirmedOrders ?? 0}
                  </div>
                  <h3>Required Daily Actions</h3>
                  <div className="daily-checklist">
                    {[
                      "Verify all next-day orders are confirmed",
                      "Call customers for unconfirmed orders",
                      "Print next-day picking lists",
                      "Prepare and label boxes with SO numbers",
                      "Prepare posts/accessories and labels",
                      "Run final quality control before preparation"
                    ].map((task) => (
                      <label key={task}>
                        <input
                          type="checkbox"
                          checked={Boolean(dailyChecklist[task])}
                          onChange={() => toggleChecklist(task)}
                        />
                        <span>{task}</span>
                      </label>
                    ))}
                  </div>
                  <h3>Next-Day Order Status</h3>
                  <table className="shortage-table">
                    <thead>
                      <tr>
                        <th>SO</th>
                        <th>Customer</th>
                        <th>Status</th>
                        <th>Ship Date</th>
                        <th>Location</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(nextDay?.orders ?? []).map((order) => (
                        <tr key={order.soNum} className={order.isConfirmed ? "" : "shortage-row"}>
                          <td>{order.soNum}</td>
                          <td>{order.customer}</td>
                          <td>{order.status || "Unknown"}</td>
                          <td>{order.shipDate}</td>
                          <td>{order.location || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              )}
            </section>
          )}
        </>
      )}
    </main>
  );
};
