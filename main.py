
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import math
import uuid
import unittest




# =========================================================
# Utility functions
# =========================================================
def ceil_hours(duration_seconds: float) -> int:
    """Round up duration (seconds) to the next full hour. Minimum billed time is 1 hour."""
    hours = duration_seconds / 3600.0
    billed = math.ceil(hours)
    return max(1, billed)


def is_weekend(dt: datetime) -> bool:
    """Return True if dt is Saturday(5) or Sunday(6)."""
    return dt.weekday() >= 5


def parse_date(yyyy_mm_dd: str) -> date:
    parts = yyyy_mm_dd.strip().split("-")
    if len(parts) != 3:
        raise ValueError("Date must be in YYYY-MM-DD format (e.g., 2026-02-11).")
    y, m, d = [int(x) for x in parts]
    return date(y, m, d)


def safe_float(prompt: str) -> float:
    while True:
        try:
            v = float(input(prompt).strip())
            if v < 0:
                print("Please enter a positive number.")
                continue
            return v
        except ValueError:
            print("Invalid number. Please try again.")


def safe_float_or_enter(prompt: str, default: float) -> float:
    """Let user press Enter to accept default."""
    while True:
        raw = input(prompt).strip()
        if raw == "":
            return float(default)
        try:
            v = float(raw)
            if v < 0:
                print("Please enter a positive number.")
                continue
            return float(v)
        except ValueError:
            print("Invalid number. Please try again.")


# =========================================================
# Abstract Base Classes (ABC)
# =========================================================
class Vehicle(ABC):
    def __init__(self, plate: str):
        self.plate = plate.strip().upper()

    @property
    @abstractmethod
    def vehicle_type(self) -> str:
        ...

    @property
    @abstractmethod
    def multiplier(self) -> float:
        ...


class Pass(ABC):
    def __init__(self, plate: str):
        self.pass_id = str(uuid.uuid4())[:8].upper()
        self.plate = plate.strip().upper()

    @property
    @abstractmethod
    def pass_type(self) -> str:
        ...

    @abstractmethod
    def is_valid(self, at_time: datetime) -> bool:
        ...


class PricingStrategy(ABC):
    @abstractmethod
    def calculate_price(
        self,
        duration_seconds: float,
        vehicle: Vehicle,
        entry_time: datetime,
        exit_time: datetime,
    ) -> float:
        ...

    @abstractmethod
    def rule_name(self) -> str:
        ...


# =========================================================
# Vehicle subclasses
# =========================================================
class Car(Vehicle):
    @property
    def vehicle_type(self) -> str:
        return "Car"

    @property
    def multiplier(self) -> float:
        return 1.0


class Motorcycle(Vehicle):
    @property
    def vehicle_type(self) -> str:
        return "Motorcycle"

    @property
    def multiplier(self) -> float:
        return 0.8


class Truck(Vehicle):
    @property
    def vehicle_type(self) -> str:
        return "Truck"

    @property
    def multiplier(self) -> float:
        return 1.5


# =========================================================
# Pass subclasses
# =========================================================
class MonthlyPass(Pass):
    def __init__(self, plate: str, start_date: date, end_date: date):
        super().__init__(plate)
        self.start_date = start_date
        self.end_date = end_date

    @property
    def pass_type(self) -> str:
        return "MonthlyPass"

    def is_valid(self, at_time: datetime) -> bool:
        today = at_time.date()
        return self.start_date <= today <= self.end_date


class WeeklyPass(Pass):
    def __init__(self, plate: str, start_date: date, end_date: date):
        super().__init__(plate)
        self.start_date = start_date
        self.end_date = end_date

    @property
    def pass_type(self) -> str:
        return "WeeklyPass"

    def is_valid(self, at_time: datetime) -> bool:
        today = at_time.date()
        return self.start_date <= today <= self.end_date


class SingleEntryPass(Pass):
    def __init__(self, plate: str):
        super().__init__(plate)
        self.used = False

    @property
    def pass_type(self) -> str:
        return "SingleEntryPass"

    def is_valid(self, at_time: datetime) -> bool:
        return not self.used

    def mark_used(self) -> None:
        self.used = True


# =========================================================
# Pricing Strategy (Hour-by-hour)
# =========================================================
class HourlyPricingStrategy(PricingStrategy):
    """
    Charges parking hour-by-hour (rounded up to full hours).
    - Weekend (Sat/Sun): $5/hr
    - Weekday Peak (08:00–18:00): $6/hr
    - Weekday Off-peak: $4/hr
    Each hour uses the rate based on that hour's timestamp.
    """

    def calculate_price(
        self,
        duration_seconds: float,
        vehicle: Vehicle,
        entry_time: datetime,
        exit_time: datetime,
    ) -> float:
        total_fee = 0.0
        billed_hours = ceil_hours(duration_seconds)

        current_time = entry_time
        for _ in range(billed_hours):
            if is_weekend(current_time):
                base_rate = 5.0
            else:
                base_rate = 6.0 if 8 <= current_time.hour < 18 else 4.0

            total_fee += base_rate * vehicle.multiplier
            current_time += timedelta(hours=1)

        return round(total_fee, 2)

    def rule_name(self) -> str:
        return "Hourly Pricing (Peak/Off-peak/Weekend)"


# =========================================================
# Core domain classes
# =========================================================
@dataclass
class ParkingSpot:
    spot_id: int
    is_occupied: bool = False
    current_plate: str | None = None

    def occupy(self, plate: str) -> None:
        self.is_occupied = True
        self.current_plate = plate.strip().upper()

    def vacate(self) -> None:
        self.is_occupied = False
        self.current_plate = None


@dataclass
class ParkingSession:
    ticket_id: str
    vehicle: Vehicle
    spot_id: int
    entry_time: datetime
    pass_used: Pass | None = None
    exit_time: datetime | None = None

    def close(self, exit_time: datetime) -> None:
        self.exit_time = exit_time

    def duration_seconds(self) -> float:
        if self.exit_time is None:
            return 0.0
        return (self.exit_time - self.entry_time).total_seconds()


@dataclass
class Receipt:
    ticket_id: str
    plate: str
    entry_time: datetime
    exit_time: datetime
    fee: float
    rule: str
    spot_id: int
    vehicle_type: str
    pass_info: str
    applied_pass_type: str | None  # pass USED or auto-detected (usage tracking)


# =========================================================
# Pass Manager
# =========================================================
class PassManager:
    """Stores passes. (Sales are logged in ParkingLot for reporting)"""

    def __init__(self):
        self._passes: dict[str, Pass] = {}

    def create_monthly_pass(self, plate: str, start_date: date, end_date: date) -> MonthlyPass:
        mp = MonthlyPass(plate, start_date, end_date)
        self._passes[mp.pass_id] = mp
        return mp

    def create_weekly_pass(self, plate: str, start_date: date, end_date: date) -> WeeklyPass:
        wp = WeeklyPass(plate, start_date, end_date)
        self._passes[wp.pass_id] = wp
        return wp

    def create_single_entry_pass(self, plate: str) -> SingleEntryPass:
        sp = SingleEntryPass(plate)
        self._passes[sp.pass_id] = sp
        return sp

    def get_pass(self, pass_id: str) -> Pass | None:
        return self._passes.get(pass_id.strip().upper())

    def find_valid_pass(self, plate: str, at_time: datetime) -> Pass | None:
        plate = plate.strip().upper()
        for p in self._passes.values():
            if p.plate == plate and p.is_valid(at_time):
                return p
        return None


# =========================================================
# Fee Calculator
# =========================================================
class FeeCalculator:
    """
    Returns: (fee, rule, pass_info, applied_pass_type)
    applied_pass_type is pass USAGE info (used or auto-detected).
    """

    def __init__(self):
        self.strategy: PricingStrategy = HourlyPricingStrategy()

    def compute_fee(self, session: ParkingSession, pass_manager: PassManager) -> tuple[float, str, str, str | None]:
        assert session.exit_time is not None, "Session must be closed before fee calculation."

        applied_pass_type: str | None = None

        # 1) If pass was explicitly used
        if session.pass_used is not None:
            p = session.pass_used

            if not p.is_valid(session.exit_time):
                pass_info = f"{p.pass_type} INVALID (charged normally)"
                applied_pass_type = None
            else:
                if isinstance(p, MonthlyPass):
                    return 0.0, "MonthlyPass Applied", "MonthlyPass VALID (fee waived)", "MonthlyPass"
                if isinstance(p, WeeklyPass):
                    return 0.0, "WeeklyPass Applied", "WeeklyPass VALID (fee waived)", "WeeklyPass"
                if isinstance(p, SingleEntryPass):
                    p.mark_used()
                    return 0.0, "SingleEntryPass Applied", "SingleEntryPass USED (fee waived)", "SingleEntryPass"

                applied_pass_type = p.pass_type
                pass_info = f"{p.pass_type} VALID"
        else:
            pass_info = "No pass"

        # 2) Auto-detect pass by plate (weekly/monthly)
        auto_p = pass_manager.find_valid_pass(session.vehicle.plate, session.exit_time)
        if isinstance(auto_p, (MonthlyPass, WeeklyPass)):
            return 0.0, "Pass Auto-Detected", f"{auto_p.pass_type} VALID (fee waived)", auto_p.pass_type

        # 3) Normal pricing
        fee = self.strategy.calculate_price(
            duration_seconds=session.duration_seconds(),
            vehicle=session.vehicle,
            entry_time=session.entry_time,
            exit_time=session.exit_time,
        )
        return fee, self.strategy.rule_name(), pass_info, applied_pass_type


# =========================================================
# Finance Module (dated revenue/expenses)
# =========================================================
@dataclass
class Debtor:
    name: str
    amount_due: float
    due_date: date

    def is_over_30_days(self, today: date) -> bool:
        return (today - self.due_date).days > 30


@dataclass
class Creditor:
    name: str
    amount_payable: float
    payable_date: date


class FinanceModule:
    """
    Requirements:
    - Calculate total expenses, revenue, profit
    - Identify debtor older than 30 days
    - Enter debtor and creditor
    - Identify creditor
    """

    def __init__(self):
        self.revenues: list[tuple[date, float, str]] = []   # (date, amount, source)
        self.expenses: list[tuple[date, float, str]] = []   # (date, amount, description)
        self.debtors: list[Debtor] = []
        self.creditors: list[Creditor] = []

    def add_revenue(self, amount: float, when: date | None = None, source: str = "Revenue") -> None:
        self.revenues.append((when or date.today(), float(amount), source))

    def add_expense(self, amount: float, when: date | None = None, description: str = "Expense") -> None:
        self.expenses.append((when or date.today(), float(amount), description))

    def total_revenue(self) -> float:
        return sum(a for _, a, _ in self.revenues)

    def total_expenses(self) -> float:
        return sum(a for _, a, _ in self.expenses)

    def profit(self) -> float:
        return self.total_revenue() - self.total_expenses()

    def add_debtor(self, debtor: Debtor) -> None:
        self.debtors.append(debtor)

    def add_creditor(self, creditor: Creditor) -> None:
        self.creditors.append(creditor)

    def debtors_over_30_days(self, today: date | None = None) -> list[Debtor]:
        t = today or date.today()
        return [d for d in self.debtors if d.is_over_30_days(t)]

    def list_creditors(self) -> list[Creditor]:
        return list(self.creditors)




# =========================================================
# Reporting Module (meets requirement wording properly)
# =========================================================
@dataclass
class PassSale:
    sold_on: date
    pass_type: str            # WeeklyPass / MonthlyPass / SingleEntryPass
    amount: float
    pass_id: str
    plate: str


class ReportGenerator:
    # ---- REQUIRED REPORTS ----
    @staticmethod
    def monthly_pass_sales_report(pass_sales: list[PassSale]) -> dict[str, dict[str, int]]:
        """
        REQUIRED: Monthly sale report for weekly pass, monthly pass, single entry pass.
        This counts PASSES SOLD (created), not pass usage.
        """
        report: dict[str, dict[str, int]] = {}
        for s in pass_sales:
            month_key = s.sold_on.strftime("%Y-%m")
            report.setdefault(month_key, {"WeeklyPass": 0, "MonthlyPass": 0, "SingleEntryPass": 0})
            if s.pass_type in report[month_key]:
                report[month_key][s.pass_type] += 1
        return report

    @staticmethod
    def monthly_car_count(receipts: list[Receipt]) -> dict[str, int]:
        """REQUIRED: number of cars each month (unique plates), based on exit month."""
        cars_by_month: dict[str, set[str]] = {}
        for r in receipts:
            month_key = r.exit_time.strftime("%Y-%m")
            cars_by_month.setdefault(month_key, set()).add(r.plate)
        return {m: len(cars) for m, cars in cars_by_month.items()}

    # ---- Finance monthly reporting (useful + aligns with finance requirement) ----
    @staticmethod
    def monthly_revenue_report(finance: FinanceModule) -> dict[str, float]:
        """Monthly revenue from ALL revenue sources (parking fees + pass sales)."""
        rev_by_month: dict[str, float] = {}
        for d, amt, _src in finance.revenues:
            month_key = d.strftime("%Y-%m")
            rev_by_month[month_key] = rev_by_month.get(month_key, 0.0) + amt
        return {m: round(v, 2) for m, v in rev_by_month.items()}

    @staticmethod
    def monthly_expense_report(finance: FinanceModule) -> dict[str, float]:
        """Monthly expenses from entered expense records."""
        exp_by_month: dict[str, float] = {}
        for d, amt, _desc in finance.expenses:
            month_key = d.strftime("%Y-%m")
            exp_by_month[month_key] = exp_by_month.get(month_key, 0.0) + amt
        return {m: round(v, 2) for m, v in exp_by_month.items()}

    @staticmethod
    def monthly_profit_report(finance: FinanceModule) -> dict[str, float]:
        """Monthly profit = monthly revenue - monthly expenses."""
        rev = ReportGenerator.monthly_revenue_report(finance)
        exp = ReportGenerator.monthly_expense_report(finance)
        all_months = set(rev.keys()) | set(exp.keys())

        out: dict[str, float] = {}
        for m in sorted(all_months):
            out[m] = round(rev.get(m, 0.0) - exp.get(m, 0.0), 2)
        return out

    # ---- Printers ----
    @staticmethod
    def print_monthly_pass_sales_report(pass_sales: list[PassSale]) -> None:
        data = ReportGenerator.monthly_pass_sales_report(pass_sales)
        print("\n====== Monthly Pass Sales Report (PASSES SOLD) ======")
        if not data or all(sum(v.values()) == 0 for v in data.values()):
            print("No pass sales recorded yet.")
            return
        for month in sorted(data.keys()):
            row = data[month]
            print(f"{month} | Weekly: {row['WeeklyPass']} | Monthly: {row['MonthlyPass']} | Single: {row['SingleEntryPass']}")
        print("====================================================\n")

    @staticmethod
    def print_monthly_car_report(receipts: list[Receipt]) -> None:
        data = ReportGenerator.monthly_car_count(receipts)
        print("\n====== Cars Per Month Report (Unique Plates) ======")
        if not data:
            print("No completed sessions yet.")
            return
        for month in sorted(data.keys()):
            print(f"{month}: {data[month]} cars")
        print("===================================================\n")

    @staticmethod
    def print_monthly_revenue_report(finance: FinanceModule) -> None:
        data = ReportGenerator.monthly_revenue_report(finance)
        print("\n====== Monthly Revenue Report (All Sources) ======")
        if not data:
            print("No revenue recorded yet.")
            return
        for month in sorted(data.keys()):
            print(f"{month}: ${data[month]:.2f}")
        print("==================================================\n")

    @staticmethod
    def print_monthly_profit_report(finance: FinanceModule) -> None:
        profit = ReportGenerator.monthly_profit_report(finance)
        rev = ReportGenerator.monthly_revenue_report(finance)
        exp = ReportGenerator.monthly_expense_report(finance)

        print("\n====== Monthly Profit Report (Revenue - Expenses) ======")
        if not profit:
            print("No profit data available yet.")
            return
        for month in profit.keys():
            print(
                f"{month} | Revenue: ${rev.get(month, 0.0):.2f} | "
                f"Expenses: ${exp.get(month, 0.0):.2f} | Profit: ${profit[month]:.2f}"
            )
        print("=======================================================\n")


# =========================================================
# Parking Lot
# =========================================================
class ParkingLot:
    """
    Meets requirements:
    - reporting: monthly pass SALES + cars per month
    - finance: revenue/expenses/profit + debtors/creditors + 30-day overdue
    - OOP: inheritance/polymorphism/encapsulation in design
    """

    def __init__(self, capacity: int = 300):
        self.capacity = capacity
        self.spots = [ParkingSpot(spot_id=i + 1) for i in range(capacity)]

        self.active_sessions_by_plate: dict[str, ParkingSession] = {}
        self.active_sessions_by_ticket: dict[str, ParkingSession] = {}

        self.completed_receipts: list[Receipt] = []

        # REQUIRED for monthly PASS SALES report
        self.pass_sales: list[PassSale] = []

        self.pass_manager = PassManager()
        self.fee_calculator = FeeCalculator()
        self.finance = FinanceModule()

    def has_availability(self) -> bool:
        return any(not s.is_occupied for s in self.spots)

    def available_count(self) -> int:
        return sum(1 for s in self.spots if not s.is_occupied)

    def allocate_spot(self, vehicle: Vehicle) -> ParkingSpot:
        for s in self.spots:
            if not s.is_occupied:
                s.occupy(vehicle.plate)
                return s
        raise RuntimeError("Parking lot is full (no spots available).")

    def release_spot(self, spot_id: int) -> None:
        if 1 <= spot_id <= self.capacity:
            self.spots[spot_id - 1].vacate()

    # ----- Pass Sales logging (PASSES SOLD) -----
    def log_pass_sale(self, pass_obj: Pass, amount: float, sold_on: date | None = None) -> None:
        sold_date = sold_on or date.today()
        sale = PassSale(
            sold_on=sold_date,
            pass_type=pass_obj.pass_type,
            amount=float(amount),
            pass_id=pass_obj.pass_id,
            plate=pass_obj.plate,
        )
        self.pass_sales.append(sale)
        # revenue from pass sale should be included in finance
        if amount > 0:
            self.finance.add_revenue(amount, sold_date, source=f"{pass_obj.pass_type} Sale")

    # ----- Sessions -----
    def start_session(self, vehicle: Vehicle, pass_id: str | None = None) -> ParkingSession:
        if vehicle.plate in self.active_sessions_by_plate:
            raise ValueError("This vehicle already has an active session.")

        if not self.has_availability():
            raise RuntimeError("No spots available (parking lot full).")

        used_pass: Pass | None = None
        if pass_id:
            p = self.pass_manager.get_pass(pass_id)
            if p is None:
                raise ValueError("Pass ID not found.")
            if p.plate != vehicle.plate:
                raise ValueError("Pass plate does not match vehicle plate.")
            used_pass = p

        spot = self.allocate_spot(vehicle)
        ticket_id = "T-" + str(uuid.uuid4())[:8].upper()

        session = ParkingSession(
            ticket_id=ticket_id,
            vehicle=vehicle,
            spot_id=spot.spot_id,
            entry_time=datetime.now(),
            pass_used=used_pass,
        )

        self.active_sessions_by_plate[vehicle.plate] = session
        self.active_sessions_by_ticket[ticket_id] = session
        return session

    def end_session(self, identifier: str) -> Receipt:
        key = identifier.strip().upper()

        session = self.active_sessions_by_ticket.get(key)
        if session is None:
            session = self.active_sessions_by_plate.get(key)

        if session is None:
            raise ValueError("No active session found for that ticket/plate.")

        exit_time = datetime.now()
        session.close(exit_time)

        fee, rule, pass_info, applied_pass_type = self.fee_calculator.compute_fee(session, self.pass_manager)

        # Finance: record PARKING FEE revenue (dated by exit day)
        if fee > 0 and session.exit_time is not None:
            self.finance.add_revenue(fee, session.exit_time.date(), source="Parking Fee")

        # release spot and remove active session
        self.release_spot(session.spot_id)
        del self.active_sessions_by_plate[session.vehicle.plate]
        del self.active_sessions_by_ticket[session.ticket_id]

        receipt = Receipt(
            ticket_id=session.ticket_id,
            plate=session.vehicle.plate,
            entry_time=session.entry_time,
            exit_time=session.exit_time,  # type: ignore[arg-type]
            fee=fee,
            rule=rule,
            spot_id=session.spot_id,
            vehicle_type=session.vehicle.vehicle_type,
            pass_info=pass_info,
            applied_pass_type=applied_pass_type,
        )

        self.completed_receipts.append(receipt)
        return receipt


# =========================================================
# Console UI
# =========================================================
def build_vehicle(vehicle_type: str, plate: str) -> Vehicle:
    vt = vehicle_type.strip().lower()
    if vt == "car":
        return Car(plate)
    if vt == "motorcycle":
        return Motorcycle(plate)
    if vt == "truck":
        return Truck(plate)
    raise ValueError("Invalid vehicle type. Use Car/Motorcycle/Truck.")


def print_receipt(r: Receipt) -> None:
    print("\n========== RECEIPT ==========")
    print(f"Ticket ID   : {r.ticket_id}")
    print(f"Plate       : {r.plate}")
    print(f"Vehicle Type: {r.vehicle_type}")
    print(f"Spot ID     : {r.spot_id}")
    print(f"Entry Time  : {r.entry_time}")
    print(f"Exit Time   : {r.exit_time}")
    print(f"Rule Applied: {r.rule}")
    print(f"Pass Info   : {r.pass_info}")
    print(f"Pass Used   : {r.applied_pass_type or 'None'}")
    print(f"Total Fee   : ${r.fee:.2f}")
    print("=============================\n")


# Suggested default pass prices (user can override)
DEFAULT_WEEKLY_PASS_PRICE = 50.0
DEFAULT_MONTHLY_PASS_PRICE = 180.0
DEFAULT_SINGLE_ENTRY_PASS_PRICE = 15.0


def main():
    lot = ParkingLot(capacity=300)

    while True:
        print("=== Urban City Parking System (Finance + Reporting) ===")
        print(f"Available spots: {lot.available_count()} / {lot.capacity}")
        print("1) Sell Monthly Pass ")
        print("2) Sell Weekly Pass ")
        print("3) Sell Single Entry Pass ")
        print("4) Vehicle Entry (Start Session)")
        print("5) Vehicle Exit (End Session)")
        print("6) Monthly Pass Sales Report (Weekly/Monthly/Single)  ")
        print("7) Cars Per Month Report                             ")
        print("8) Monthly Revenue Report ")
        print("9) Monthly Profit Report (Revenue - Expenses)")
        print("10) Add Expense (with date)")
        print("11) Add Debtor")
        print("12) Add Creditor")
        print("13) Show Debtors > 30 days")
        print("14) Show Creditors")
        print("15) Finance Summary (Total Revenue/Expenses/Profit)")
        print("0) Exit Program")

        choice = input("Choose an option: ").strip()

        try:
            if choice == "1":
                plate = input("Enter plate number: ")
                start = parse_date(input("Start date (YYYY-MM-DD): "))
                end = parse_date(input("End date (YYYY-MM-DD): "))
                price = safe_float_or_enter(
                    f"Monthly pass sale price (Enter for default ${DEFAULT_MONTHLY_PASS_PRICE:.2f}): ",
                    DEFAULT_MONTHLY_PASS_PRICE,
                )
                mp = lot.pass_manager.create_monthly_pass(plate, start, end)
                lot.log_pass_sale(mp, price)
                print("\nMonthly pass SOLD & recorded.")
                print(f"Pass ID: {mp.pass_id} | Plate: {mp.plate} | {mp.start_date} to {mp.end_date} | Price: ${price:.2f}\n")

            elif choice == "2":
                plate = input("Enter plate number: ")
                start = parse_date(input("Start date (YYYY-MM-DD): "))
                end = parse_date(input("End date (YYYY-MM-DD): "))
                price = safe_float_or_enter(
                    f"Weekly pass sale price (Enter for default ${DEFAULT_WEEKLY_PASS_PRICE:.2f}): ",
                    DEFAULT_WEEKLY_PASS_PRICE,
                )
                wp = lot.pass_manager.create_weekly_pass(plate, start, end)
                lot.log_pass_sale(wp, price)
                print("\nWeekly pass SOLD & recorded.")
                print(f"Pass ID: {wp.pass_id} | Plate: {wp.plate} | {wp.start_date} to {wp.end_date} | Price: ${price:.2f}\n")

            elif choice == "3":
                plate = input("Enter plate number: ")
                price = safe_float_or_enter(
                    f"Single entry pass sale price (Enter for default ${DEFAULT_SINGLE_ENTRY_PASS_PRICE:.2f}): ",
                    DEFAULT_SINGLE_ENTRY_PASS_PRICE,
                )
                sp = lot.pass_manager.create_single_entry_pass(plate)
                lot.log_pass_sale(sp, price)
                print("\nSingle entry pass SOLD & recorded.")
                print(f"Pass ID: {sp.pass_id} | Plate: {sp.plate} | Price: ${price:.2f}\n")

            elif choice == "4":
                plate = input("Plate number: ")
                vtype = input("Vehicle type (Car/Motorcycle/Truck): ")
                pass_id = input("Pass ID (press Enter if none): ").strip()
                vehicle = build_vehicle(vtype, plate)

                session = lot.start_session(vehicle, pass_id if pass_id else None)
                print("\nVehicle entered successfully!")
                print(f"Ticket ID: {session.ticket_id}")
                print(f"Spot ID  : {session.spot_id}")
                print(f"Entry    : {session.entry_time}\n")

            elif choice == "5":
                identifier = input("Enter Ticket ID or Plate: ")
                receipt = lot.end_session(identifier)
                print_receipt(receipt)

            # REQUIRED REPORTS
            elif choice == "6":
                ReportGenerator.print_monthly_pass_sales_report(lot.pass_sales)

            elif choice == "7":
                ReportGenerator.print_monthly_car_report(lot.completed_receipts)

            # Finance reports
            elif choice == "8":
                ReportGenerator.print_monthly_revenue_report(lot.finance)

            elif choice == "9":
                ReportGenerator.print_monthly_profit_report(lot.finance)

            elif choice == "10":
                amt = safe_float("Expense amount: ")
                d_raw = input("Expense date (YYYY-MM-DD) or press Enter for today: ").strip()
                exp_date = parse_date(d_raw) if d_raw else date.today()
                desc = input("Expense description (e.g., maintenance, salary, electricity): ").strip() or "Expense"
                lot.finance.add_expense(amt, exp_date, description=desc)
                print("Expense added.\n")

            elif choice == "11":
                name = input("Debtor name: ").strip()
                amt = safe_float("Amount due: ")
                due = parse_date(input("Due date (YYYY-MM-DD): "))
                lot.finance.add_debtor(Debtor(name=name, amount_due=amt, due_date=due))
                print("Debtor added.\n")

            elif choice == "12":
                name = input("Creditor name: ").strip()
                amt = safe_float("Amount payable: ")
                pay_date = parse_date(input("Payable date (YYYY-MM-DD): "))
                lot.finance.add_creditor(Creditor(name=name, amount_payable=amt, payable_date=pay_date))
                print("Creditor added.\n")

            elif choice == "13":
                overdue = lot.finance.debtors_over_30_days()
                print("\n--- Debtors Over 30 Days ---")
                if not overdue:
                    print("None found.\n")
                else:
                    for d in overdue:
                        days = (date.today() - d.due_date).days
                        print(f"{d.name} | Due ${d.amount_due:.2f} | {days} days overdue | Due date: {d.due_date}")
                    print()

            elif choice == "14":
                creditors = lot.finance.list_creditors()
                print("\n--- Creditors ---")
                if not creditors:
                    print("None found.\n")
                else:
                    for c in creditors:
                        print(f"{c.name} | Payable ${c.amount_payable:.2f} | Pay date: {c.payable_date}")
                    print()

            elif choice == "15":
                print("\n--- Finance Summary (Totals) ---")
                print(f"Total Revenue : ${lot.finance.total_revenue():.2f}")
                print(f"Total Expenses: ${lot.finance.total_expenses():.2f}")
                print(f"Profit        : ${lot.finance.profit():.2f}\n")

            elif choice == "0":
                print("Goodbye!")
                break

            else:
                print("Invalid choice.\n")

        except Exception as ex:
            print(f"\nERROR: {ex}\n")


# =========================================================
# Unit Tests (Required by guideline: use test library)
# =========================================================
class TestParkingFinanceReports(unittest.TestCase):
    def test_finance_profit(self):
        fm = FinanceModule()
        fm.add_revenue(200, date(2026, 1, 5), source="Parking Fee")
        fm.add_expense(50, date(2026, 1, 6), description="Maintenance")
        self.assertEqual(fm.profit(), 150)

    def test_debtor_over_30_days(self):
        fm = FinanceModule()
        old_due = date.today() - timedelta(days=31)
        fm.add_debtor(Debtor("John", 100, old_due))
        self.assertEqual(len(fm.debtors_over_30_days()), 1)

    def test_monthly_pass_sales_report(self):
        sales = [
            PassSale(date(2026, 1, 10), "WeeklyPass", 50, "AAAA1111", "ABC123"),
            PassSale(date(2026, 1, 11), "WeeklyPass", 50, "BBBB2222", "XYZ999"),
            PassSale(date(2026, 1, 20), "MonthlyPass", 180, "CCCC3333", "CAR777"),
        ]
        rep = ReportGenerator.monthly_pass_sales_report(sales)
        self.assertEqual(rep["2026-01"]["WeeklyPass"], 2)
        self.assertEqual(rep["2026-01"]["MonthlyPass"], 1)


if __name__ == "__main__":
    unittest.main()

    #main()

