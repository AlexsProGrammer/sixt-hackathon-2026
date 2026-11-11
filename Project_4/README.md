# Project 4: Fleet Allocation Challenge

**Project owners:** Sara Michetti, Julian Mehne

**Questions before the hackathon:** email the project owners directly: sara.michetti@sixt.com, julian.mehne@sixt.com. On the day, technical support is available on site and domain expertise remotely; the on-site team will coordinate.

## 1. The task

A car rental company runs ten stations in a fictional region with three towns: Marlow, Dunmere and Highvale.
Two stations are at airports, the others are downtown.
The company has four car categories: economy, compact, midsize and premium.

Some stations have too many cars for the next 14 days, others too few.
Your team plans three types of action for these 14 days:

- **Fleet addition**: a new car comes early to a station. It costs money.
- **Fleet removal**: an idle car goes back to its owner early. It saves holding cost.
- **Transfer**: a driver or a truck moves cars to another station. It takes 1 or 2 days and costs money.

Cars that are already on rent or booked must stay available for these rentals.
The other cars serve new demand.
You do not know the new demand.
You estimate it from 8 weeks of rental history.

The goal is the highest profit over the 14 days.
You have about five hours, in teams of three.

## 2. Terms

- **Station**: a rental branch. Its type is airport or downtown.
- **Car category**: economy < compact < midsize < premium. The order matters for upgrades.
- **Day**: day 1 to day 14 of the plan. Day 1 is a Monday.
- **Station fleet**: on a given day, the idle cars of a station plus the cars on rent that were picked up there.
- **Committed car-days**: car-days of open rentals (picked up, not yet returned) and of future bookings (booked before day 1, picked up on or after day 1).
- **Demand to come**: car-days of rentals that are not booked before day 1.
- **Base revenue per car-day**: the revenue per car-day if the company serves all demand. It differs by station and category.
- **Price factor**: the average price, relative to the base revenue, if the company serves only a share of the demand to come.
  Serving less allows a higher price.
- **Fare adjustment**: the conversion of the price factors into demand buckets, each with its own revenue per additional car-day (Appendix C).

## 3. What you get

All data is simulated.
The data files are in `data/`.
Appendix B lists all columns.

| Topic            | File                 | Content                                                                                                |
| ---------------- | -------------------- | ------------------------------------------------------------------------------------------------------ |
| Horizon          | `horizon.csv`        | First and last date of the 14 days.                                                                    |
| Network          | `stations.csv`       | Station type, position and maximum utilization.                                                        |
|                  | `distances.csv`      | Road distance and transfer lead time between two stations.                                             |
| Fleet            | `fleet_snapshot.csv` | Each car at the start of day 1: idle at a station, or on rent.                                         |
| Rentals          | `reservations.csv`   | Completed rentals of the last 8 weeks, open rentals and future bookings, each with its revenue.        |
| Costs and prices | `categories.csv`     | Holding cost per car-day, addition cost, and the caps on additions and removals per category.          |
|                  | `transfer_costs.csv` | Cost of a driver and of a truck.                                                                       |
|                  | `price_factors.csv`  | Price factor for serving 60, 70, 80, 90 or 100 % of the demand to come, per station type and category. |
| Checks           | `check_values.csv`   | Correct Level 0 values for 10 station, category and date cells.                                        |

You also get:

- `fleetkit/`: helper code that reads and checks the data and writes a plan (Appendix D).
- `starter.py`: loads the data, makes the baseline plan and shows a small optimization model.
- `plans/do_nothing.csv`: the plan with no action.
- `requirements.txt`: Python 3.14 or newer with pandas, pandera and PuLP with the CBC solver.
  You can use any other tool or solver.

You do not get the demand to come or the base revenue per car-day.
Estimate both from the completed rentals.
A simple first forecast: for each station, category and weekday, take the mean number of cars on rent in the history, and subtract the committed car-days.
The history contains only rentals that were picked up in the last 8 weeks.

## 4. What you hand in

### The plan

A plan is a CSV file with these columns:

| Column | Content |
| --- | --- |
| `action` | `add`, `remove` or `transfer` |
| `date` | ISO date inside the 14 days; for a transfer, the departure date |
| `category` | `economy`, `compact`, `midsize` or `premium` |
| `station_id` | the station of the addition or removal, or the origin of the transfer |
| `to_station_id` | the destination of a transfer; empty for `add` and `remove` |
| `mode` | `driver` or `truck` for a transfer; empty for `add` and `remove` |
| `cars` | number of cars, an integer of at least 1 |

Example:

```
action,date,category,station_id,to_station_id,mode,cars
add,2027-03-01,economy,S03,,,2
remove,2027-03-04,premium,S07,,,1
transfer,2027-03-02,compact,S01,S05,driver,1
```

Rows with the same values add up.
A plan with only the header is the do-nothing plan.
Rentals are not part of the plan.
The scorer calculates them.
A plan is always per category.
If you plan the total fleet, `fleetkit.split_total_plan` converts it into a plan per category.

### A valid plan

A plan is valid if:

1. At each station, in each category and on each day, the station fleet is at least the committed car-days.
   Open rentals and bookings always keep their car.
2. The additions of a category are at most its `addition_cap`, and the removals at most its `removal_cap`.
   The caps apply to all stations and all 14 days together.
3. All stations, categories, dates and modes exist, and no transfer goes to its own origin.

Validity depends only on your data.
A plan that is valid in the feedback round is also valid in the final ranking.
An invalid final plan ranks last.

### Submission

1. Write the plan with `fleetkit.write_plan`. It checks the format, not the validity.
2. Copy the file into your team folder in the shared folder. Use a new file name for each submission, for example `level1_v2.csv`.
3. Within about a minute, `level1_v2.result.md` appears next to it.
   It shows if the plan is valid, up to 50 violations, and for a valid plan the profit with its totals: committed revenue, new revenue, holding cost, addition cost, transfer cost, and the number of cars added, removed and transferred.
4. `leaderboard.md` in the shared folder shows the best profit of each team, and the profits of the do-nothing plan and the baseline plan.
5. Before the deadline, put your final plan into your team folder as `final.csv`.

## 5. How your plan is scored

The scorer applies these rules for each station, category and day.
Appendix A gives the exact rules.

- Your actions and the one-way rentals change the station fleet from day to day.
  A one-way rental moves its car to the return station on the day after the return.
- A transfer leaves on its departure date and arrives after the lead time (1 or 2 days).
  On the way, the car earns nothing.
- Committed car-days use cars of their own category only.
- New demand can use at most maximum utilization × station fleet − committed car-days.
  If the committed car-days are higher, the station serves no new demand on that day.
- New demand is served with cars of its own category first.
  Free cars of the next higher category serve the rest, at the revenue of the requested category (upgrade).
- The revenue of new demand follows the price factors: if the station serves less of the demand, the average price is higher (Appendix C).
- Each car in the fleet costs holding cost on each day: idle, on rent or in transit.
  An added car costs the addition cost once.
  A driver transfer costs per car.
  A truck costs per truck, and one truck carries up to 8 cars of any category on the same route and day.
- Profit = revenue − holding cost − addition cost − transfer cost.
  The fleet position after day 14 has no value.

In the feedback round, the scorer uses one public demand scenario.
For the final ranking, it uses 30 hidden scenarios from the same random process, and your score is the mean profit.
Two scores that differ by less than 2 standard errors are a tie.
Do not fit your plan to the public scenario: it is only one draw.

## 6. Levels

The rules and the scorer are the same on all levels.
One model per category can cover all levels; each level adds features to it.

- **Level 0, data**: find the station fleet, the committed car-days and the one-way arrivals and departures per station, category and day.
  Forecast the demand to come and the base revenue.
  Compare your results with `check_values.csv`.
  If you are stuck, ask the organizers for the Level 0 results.
- **Level 1, fleet size**: plan additions and removals, without transfers.
  Beat the baseline plan.
- **Level 2, transfers by driver**: model a time-space network with stations and days as nodes and transfers as arcs.
  You can simplify, for example with the total fleet or with only the peak days.
- **Level 3, categories and trucks**: model upgrades between categories and trucks with 8 places.
- **Level 4, bonus**: make the plan robust against forecast errors.
  The scorer uses the price factors exactly as given.
  Check each set of price factors with the fare adjustment, and decide what to do if a set does not behave as expected.

## 7. Judging

- 60 %: rank of your final plan on the hidden scenarios.
- 40 %: jury assessment of your model and your presentation.

---

# Appendix A: exact scoring rules

Index: station s, category k, day d = 1 to 14.

**R1. Committed car-days c[s,k,d].**
Each open or booked rental occupies one car of its category at its pickup station on each day from max(pickup day, day 1) to min(return day, day 14), both days included.
Completed rentals do not count.

**R2. One-way rentals.**
Only open rentals and future bookings can be one-way (return station different from pickup station).
Demand to come returns to its pickup station.
A one-way rental occupies a car at the pickup station until its return day.
On the day after the return day, the car leaves the fleet of the pickup station and joins the fleet of the return station.
If that day is after day 14, nothing changes inside the horizon.

**R3. Fleet.**
Let f[s,k,0] be the station fleet at the start of day 1, before your plan: idle snapshot cars at s plus snapshot cars on rent whose rental was picked up at s.
Then for each day:

f[s,k,d] = f[s,k,d-1] + one-way arrivals − one-way departures + fleet additions − fleet removals + transfers arriving − transfers leaving.

**R4. Plan effects.**
A fleet addition or removal on date d changes the fleet from day d on.
A transfer leaves the origin fleet on its departure day d.
It joins the destination fleet on day d + lead time (`distances.csv`).
A transfer that arrives after day 14 never arrives inside the horizon.
A car in transit earns no revenue.

**R5. Validity.**
A plan is valid if all of these hold:

- f[s,k,d] ≥ c[s,k,d] for every station, category and day.
- The fleet additions of each category sum to at most `addition_cap` of that category. The fleet removals sum to at most `removal_cap`.
- All station ids, categories, dates and modes exist. Dates are inside the horizon. Car counts are integers of at least 1. A transfer does not go to its own station.

**R6. Free capacity for demand to come.**
a[s,k,d] = max(0, max_utilization[s] × f[s,k,d] − c[s,k,d]) (a real number).
Cars on rent from demand to come never exceed a[s,k,d].
The maximum utilization is only a limit on this demand. It is not a validity rule.

**R7. Serving demand to come.**
Let D[s,k,d] be the demand to come: the number of cars on rent on day d from rentals that are not booked before day 1, at the pickup station.
For each station and day, from the lowest category to the highest:

1. Own demand first: own[k] = min(D[k], a[k]).
2. The cars of category k that are still free (a[k] − own[k]) serve the demand of the next lower category k−1 that is still unserved: up[k] = min(a[k] − own[k], D[k−1] − own[k−1]).
3. Served demand of category k: served[k] = own[k] + up[k+1] (nothing above premium).

An upgraded rental earns the revenue of the requested category.
There is no upgrade by two categories.
Committed car-days use cars of their own category. Only demand to come is upgraded.

**R8. Revenue of demand to come.**
If the company serves the share q of the true demand D at a station, category and day, the revenue is q × D × base × price factor(q).
Here base is the base revenue per car-day of that scenario, station and category.
The price factors are given for the shares 60 %, 70 %, 80 %, 90 % and 100 %.
Below 60 % the price factor of 60 % applies.
Between two listed shares, the revenue is linear in the served car-days.
If D is 0, the revenue is 0.
The scorer uses the price factors exactly as given.

**R9. Revenue of committed rentals.**
Each open or booked rental earns its `revenue` × (its car-days inside the horizon ÷ all its car-days).
This revenue does not depend on your plan.

**R10. Costs.**

- Holding cost: for each category, `holding_cost_per_day` × (cars of that category in a station fleet or in transit), summed over all 14 days.
  This includes cars on rent.
- Fleet addition cost: `addition_cost_per_car` × added cars.
- Driver transfer cost: cars × (fixed cost + cost per km × distance).
- Truck transfer cost: for each origin, destination and departure day, trucks = ceil(cars sent by truck ÷ 8). Cost = trucks × (fixed cost + cost per km × distance). Cars of different categories share a truck.

**R11. Profit.**
Profit = committed revenue + revenue of demand to come − holding cost − fleet addition cost − transfer cost.
There is no value and no penalty for the fleet position at the end of day 14.
Revenue includes all variable rental costs.

# Appendix B: data columns

All files are CSV.
Dates are ISO dates.

| File | One row per | Columns |
| --- | --- | --- |
| `horizon.csv` | the horizon | `first_date`, `last_date` |
| `stations.csv` | station | `station_id`, `station_name`, `station_type` (airport, downtown), `x_km`, `y_km`, `max_utilization` |
| `distances.csv` | ordered pair of different stations | `from_station_id`, `to_station_id`, `distance_km` (road), `lead_time_days` (1 or 2) |
| `categories.csv` | car category | `category`, `rank` (1 = lowest), `holding_cost_per_day`, `addition_cost_per_car`, `addition_cap`, `removal_cap` |
| `transfer_costs.csv` | transfer mode | `mode`, `fixed_cost`, `cost_per_km`, `capacity` (driver 1, truck 8); fixed and per-km cost are per car for the driver and per truck for the truck |
| `price_factors.csv` | station type, category and share | `station_type`, `category`, `served_share` (0.6 to 1.0), `price_factor` (1.0 at share 1.0) |
| `fleet_snapshot.csv` | car at the start of day 1 | `vehicle_id`, `category`, `status` (idle, on_rent), `station_id` (idle only), `reservation_id` (on rent only) |
| `reservations.csv` | reservation | `reservation_id`, `category`, `pickup_station_id`, `pickup_date`, `return_station_id`, `return_date`, `booking_date`, `revenue`, `status` |
| `check_values.csv` | station, category and date cell | `station_id`, `category`, `date`, `committed_car_days`, `oneway_arrivals`, `oneway_departures`, `station_fleet` (the station fleet on that date with the do-nothing plan) |

Reservation groups (`status`):

- `completed`: picked up in the 8 weeks before day 1 and returned before day 1. All are round trips.
- `open`: picked up before day 1, returned on or after day 1. Each open rental has exactly one car on rent in the snapshot.
- `booked`: booked before day 1, picked up on or after day 1.

`revenue` is the revenue of the whole rental.
A rental occupies a car on each day from the pickup date to the return date, both included.
The history shows demand at the base price: the fleet was large enough in the past, so no demand was lost.

# Appendix C: the fare adjustment, a worked example

The price factors tell you how the average price changes with the share of demand that you serve.
Take one station, one category and one day with demand D = 100 car-days and base revenue 250 per car-day.
The price factors are:

| Served share q | 60 % | 70 % | 80 % | 90 % | 100 % |
| --- | --- | --- | --- | --- | --- |
| Price factor | 1.30 | 1.21 | 1.14 | 1.07 | 1.00 |

Total revenue at share q is q × D × 250 × price factor(q):

| Served share q | 60 % | 70 % | 80 % | 90 % | 100 % |
| --- | --- | --- | --- | --- | --- |
| Total revenue | 19500 | 21175 | 22800 | 24075 | 25000 |

The fare adjustment turns this into buckets.
Each bucket is a slice of demand with its own revenue per additional car-day (marginal revenue):

| Bucket | Car-days in the bucket | Revenue added | Marginal revenue per car-day |
| --- | --- | --- | --- |
| 0 to 60 % | 60 | 19500 | 325.00 |
| 60 to 70 % | 10 | 1675 | 167.50 |
| 70 to 80 % | 10 | 1625 | 162.50 |
| 80 to 90 % | 10 | 1275 | 127.50 |
| 90 to 100 % | 10 | 925 | 92.50 |

Serving 75 car-days earns 19500 + 1675 + 0.5 × 1625 = 21987.50.
This is the same value as the linear interpolation between 21175 and 22800.
Serving 40 car-days earns 40 × 250 × 1.30 = 13000.

Here the marginal revenue falls from bucket to bucket.
Then a linear program can model the revenue with one variable per bucket, bounded by the bucket size.
It fills the buckets with high marginal revenue first, which is correct.
If the marginal revenue rises somewhere, a linear program fills a later bucket before an earlier one and overstates the revenue.

# Appendix D: helper code in `fleetkit`

- `load_instance(data_dir=...)` reads and checks all data files. It returns one table per file.
- `write_plan(df_plan=..., path=...)` checks the plan format and writes the CSV.
- `baseline_plan(instance=...)` makes the baseline plan (a simple Level 1 rule, no optimization).
  For each station and category it takes need = (pickups per day in the history × average rental length of the category) ÷ maximum utilization, and the current fleet = idle cars plus cars on rent picked up there.
  It adds max(0, need − current) cars on day 1, scaled down to the addition cap.
  The baseline plan only adds cars, so it is always valid.
- `split_total_plan(df_total_plan=..., instance=...)` converts a plan for the total fleet (columns `action, date, station_id, to_station_id, mode, cars`) into a plan per category.
  It splits the cars of each row in proportion to the categories at the origin station on day 1.
  A station without cars uses the shares of the whole network.

The code does not compute committed car-days, one-way flows or fleets over the 14 days.
That is the Level 0 task.

---

## Setup

<p align="center"><img src="../assets/time-quick-setup.svg" alt="About 10 minutes" width="420"></p>

**Quick setup (about 10 min):** `bash setup.sh` in this folder. It makes a virtual environment, installs the packages and runs `starter.py`. Python is our starting point; any language is fine.
Do this **before the hackathon day** (repo is shared on 12 Nov).

- `git` and **Python 3.14 or newer**, with a virtual environment (`python -m venv .venv` or `uv venv`).
- Your own LLM coding agent, so you can work with the tool you are most comfortable with. SIXT provides LLM API keys for tasks that need one.
- Install the dependencies: `pip install -r Project_4/requirements.txt`. Add your own to that file. Never commit secrets (use `.env`).
- Data: in `Project_4/data/`. Try `python Project_4/starter.py` to check your setup.
- Check: you can clone or fork the repo and run `python --version` in your environment.

## Submission
Code, a `SUBMISSION.md` in this folder (approach, results, how to run) and evaluation results.
Also **either** a **1-minute demo video** (`submission/demo.mp4`, under 50 MB) **or** a **small set of slides** (`submission/slides.pdf`, max 5 slides) in your project folder, included in your repo.
