import { FormEvent, useEffect, useMemo, useState } from "react";
import { ShortageTable } from "../components/ShortageTable";
import { apiClient } from "../lib/api";
import type { LocationOption, ShortageReportResponse, UserInfo } from "../lib/types";

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
  const defaults = useMemo(defaultDateRange, []);
  const [me, setMe] = useState<UserInfo | null>(null);
  const [locations, setLocations] = useState<LocationOption[]>([]);
  const [report, setReport] = useState<ShortageReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [locationId, setLocationId] = useState<string>("");
  const [startDate, setStartDate] = useState(defaults.startDate);
  const [endDate, setEndDate] = useState(defaults.endDate);
  const [expandedOrders, setExpandedOrders] = useState<Record<string, boolean>>({});
  const [expandedKits, setExpandedKits] = useState<Record<string, boolean>>({});

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
      const [locationsPayload, reportPayload] = await Promise.all([
        apiClient.getLocations(token),
        apiClient.getShortages(token, filters)
      ]);
      setLocations(locationsPayload.locations);
      setReport(reportPayload);
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
          <img src="/logo.svg" alt="Quai" className="navbar-brand-logo" />
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

          {report.orders.length === 0 ? (
            <section className="card">
              <div className="state-box">No shortages found for the selected filters.</div>
            </section>
          ) : (
            <section className="card">
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
            </section>
          )}
        </>
      )}
    </main>
  );
};
