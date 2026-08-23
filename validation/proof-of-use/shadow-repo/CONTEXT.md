# montecarlo-pricing

A toolkit for pricing exotic options with Monte Carlo simulation.

## Language

**Seed**:
The fixed integer that initializes the random number generator so a
simulation run is exactly reproducible.
_Avoid_: random state

**Backlog**:
The single ordered list where all pending work on this project is recorded.
_Avoid_: issue tracker, todo list

**Run**:
One complete Monte Carlo execution: a seed, a scenario, and the resulting
price distribution.
_Avoid_: job, simulation instance

**Scenario**:
The market assumptions a run prices against — volatility surface, rate
curve, dividend schedule.
_Avoid_: config, parameters
