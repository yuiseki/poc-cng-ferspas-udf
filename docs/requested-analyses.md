# Ten analyses requested by an agricultural analyst

These came from an agricultural scientist who advises smallholder programmes
and agriculture ministries, asked what global maps would help them work. They
were written without sight of this repository or of what data is available, so
they are what the field actually wants rather than what is easy. They have been
filtered here to the ones this server can compute, and the reduction made to
each one is stated.

Everything reads the AgERA5 monthly collections unless stated:

| collection | unit | span |
| --- | --- | --- |
| `AGERA5-PF-M` | mm/month | 1979-01 to 2026-07, 571 frames |
| `AGERA5-ET0-M` | mm/month | same |
| `AGERA5-TMAX-AVG-M` | K | same |
| `AGERA5-TMIN-AVG-M` | K | same |

Daily collections exist for the same span and add relative humidity
(`AGERA5-RH06/09/12/15/18`, %), solar radiation (`AGERA5-SRF`) and wind
(`AGERA5-WS`).

## 1. month-percentile

Where does this month's rainfall sit in the record for this same calendar
month? Percentile, 0 to 100, diverging about 50.

Percentage-of-normal misleads in dry places, where 60 percent of normal can be
an ordinary year. A percentile is what lets a district officer say "the second
driest July in forty years" and survive scrutiny, and it is how drought
declarations are argued.

Compute: rank this month's rainfall among the same calendar month of every year
in the record, as an empirical percentile.

Reduced from: the request wanted seasonal totals and SPI/SPEI companions. A
single month is the same idea at the resolution the monthly data supports.

## 2. dependable-rainfall

How much rain can a farmer count on here in four years out of five? The 20th
percentile of this calendar month's rainfall across the record, in mm.
Sequential.

Farmers and any honest investment appraisal plan against the dependable amount,
not the mean. It decides where to promote rainfed maize against drought
tolerant small grains, and it sizes water harvesting.

Compute: the 20th percentile of the same calendar month over all years.

## 3. rainfall-variability

How unreliable is the rain here? Coefficient of variation of this calendar
month's rainfall across the record, as a percentage. Sequential. Mark 30
percent, above which rainfed cropping is conventionally marginal.

Rising variability with a flat mean is a real and commonly reported pattern,
and it changes risk without changing any average.

Compute: standard deviation over mean, per pixel, across the same calendar
month of every year.

## 4. consecutive-dry-months

How long does this place go without usable rain? The longest run of dry months
within the last twelve, where a dry month is one whose rainfall is under half
its reference evapotranspiration. Sequential, 0 to 12.

Distinguishes a place with one long predictable dry season, which farmers
manage by storing grain, from one subject to multi-season failure, which needs
destocking plans and a different kind of safety net.

Compute: for each of the last twelve months flag `P < 0.5 * ET0`, then take the
longest consecutive run.

Reduced from: the request wanted the long-run mean and the worst case over the
whole record. A rolling twelve months is the part that fits.

## 5. aridity-annual

Can rain meet the atmospheric demand over a whole year here? The UNEP aridity
index, the sum of twelve months of rainfall over the sum of twelve months of
reference evapotranspiration. Sequential, 0 to 1. The class boundaries are
hyper-arid under 0.05, arid to 0.20, semi-arid to 0.50, dry sub-humid to 0.65,
humid above.

Dryland classification drives eligibility for climate finance and whether
rainfed cereal production is defensible at all.

Compute: twelve months of each, summed, divided.

Note: this repository already has a monthly `aridity`. The index is defined
annually, and the analyst was explicit about that, so this is the version their
field would recognise. Say so in the notes rather than quietly having two.

## 6. fournier-erosivity

How erosive is the rain here? The modified Fournier index, the sum over twelve
months of monthly rainfall squared, divided by the annual total, in mm.
Sequential.

Justifies terracing, contour bunding and cover crops, and identifies when bare
soil is most dangerous, which is the interval between land preparation and
canopy closure.

Compute: `sum(P_m^2) / sum(P_m)` over the last twelve months.

Reduced from: the RUSLE R factor needs sub-hourly intensity. The modified
Fournier index is the accepted regional fallback and is computable from monthly
totals alone. Do not call the output an R factor.

## 7. gdd-shift

Can a longer-duration, higher-yielding variety grow here now than twenty years
ago? Growing degree days for this month minus growing degree days for the same
month twenty years ago, in degree-days. Diverging about zero.

Variety recommendation. In highland East Africa and the Andes it shows land
becoming thermally viable, which is both an opportunity and a deforestation
risk worth flagging.

Compute: for each date, `sum(max(0, (Tmax + Tmin) / 2 - base))` over the days of
the month, with base 10 C for maize. Cap Tmax at 30 C before averaging, which is
the conventional correction and matters in hot lowlands. Subtract.

## 8. night-warming

Are the nights getting warmer here? This month's mean minimum temperature minus
the mean of the same calendar month over 1979 to 1998, in K. Diverging about
zero.

Each degree of night warming costs roughly a tenth of rice yield through
respiration, and the mechanism is invisible if only daytime maxima are looked
at. It reframes a South Asian conversation from drought to heat.

Compute: mean of the same calendar month over the first twenty years of the
record, subtracted from this month.

## 9. livestock-heat

How hard is the heat on cattle here? The Temperature Humidity Index, from the
daily maximum temperature and afternoon relative humidity. Sequential. The
operational classes are mild from 72, moderate from 80, severe from 90.

Heat stress cuts milk yield, conception rates and feed intake before it kills
anything, so it is chronically under-reported. It informs shade and water point
investment and the choice between exotic and indigenous dairy breeds.

Compute, with T in Celsius and RH in percent, the standard NRC form:

    THI = (1.8 * T + 32) - (0.55 - 0.0055 * RH) * (1.8 * T - 26)

Use the daily collections `AGERA5-TMAX` and `AGERA5-RH15`, since the afternoon
peak is what matters.

Reduced from: the request wanted a count of stress days per year weighted by
cattle density. A single day is what one tile request can read.

## 10. months-since-rain

How long since this place last had meaningful rain? The number of months since
the most recent month with more than 20 mm, counted back over the last
twenty-four. Sequential, 0 to 24.

Crude, and closely matched to how pastoralists describe conditions themselves.
Drives early destocking advice, emergency water trucking and the anticipation of
pastoral movement across borders, which becomes a conflict issue if nobody saw
it coming.

Compute: walk back through the months until `P > 20`; report how many months
that took.

## Requests that were dropped, and why

The analyst asked for nineteen. The nine not listed above need either daily
data across many years, or per-year date searching, which one tile request
cannot read:

- **Rainy season onset, and its drift** need a per-year scan of daily or dekadal
  rainfall for a 20 mm in 3 days trigger with a false-start guard. One year is
  about 36 dekadal frames; a median across forty years is 1,440.
- **In-season dry spell risk during flowering** needs daily rainfall across many
  years. The analyst said plainly there is no honest monthly fallback, and
  agreed it should be refused rather than approximated.
- **Heat stress days at flowering**, **WRSI**, **repeat failure return period**,
  **aflatoxin risk**, **rangeland forage days** and **compound soil and dry
  spell vulnerability** all need either daily windows across years, a crop
  calendar, or a soil layer on another grid.
- The **bivariate** rendering the analyst asked for in one of them does not fit
  the two colour scales this server guarantees.

Worth saying: the analyst ranked onset, WRSI, percentile and repeat failure as
what they would build first. Only the percentile survived the filter. That gap
between what is wanted and what a per-tile server can compute is the honest
finding, not a failure of the request.
