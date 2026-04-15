export type UserInfo = {
  username: string;
  email?: string | null;
  roles: string[];
};

export type ShortageComponent = {
  itemId: number;
  itemName: string;
  orderedQty: number;
  onHandQty: number;
  remainingStock: number;
};

export type ShortageLine = {
  itemId: number;
  itemName: string;
  date?: string | null;
  orderedQty: number;
  onHandQty?: number | null;
  remainingStock?: number | null;
  isKit: boolean;
  components: ShortageComponent[];
};

export type ShortageOrder = {
  soNum: string;
  customer: string;
  serviceType: string;
  date?: string | null;
  totalOrdered: number;
  lines: ShortageLine[];
};

export type ShortageReportResponse = {
  locationId?: number | null;
  startDate: string;
  endDate: string;
  orders: ShortageOrder[];
  totalOrders: number;
  asOf: string;
};

export type LocationOption = {
  id: number;
  name: string;
};

export type LocationOptionsResponse = {
  locations: LocationOption[];
};
