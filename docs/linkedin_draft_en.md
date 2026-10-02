# LinkedIn draft

Where should the timer start when comparing data-processing tools?

I compared Python loops, pandas and SQLite using identical deterministic synthetic data. My study covers filtering, grouped aggregation and JOIN followed by aggregation, with 270 main trials after a small pilot.

One result makes the timing boundary concrete. For a 50,000-row filter, the warm median was 1.13 ms for Python and 1.35 ms for pandas. Include source loading and backend preparation, and the order changes: pandas took 3.42 ms while Python took 9.94 ms.

At one million rows, pandas had the lowest median elapsed time across the tested operations and modes. Memory told another story: the warm JOIN used a median 128.91 MiB of peak worker RSS in SQLite versus 229.83 MiB in pandas, while taking 317.70 ms versus 28.05 ms.

My main takeaway: define the work being timed before choosing a tool. Setup costs, repeated execution and memory limits can lead to different decisions.

These results describe one Apple M3 MacBook Air, one integer schema and five repeats per condition. They are not a universal ranking. Energy was not measured. The repository includes raw observations, exact-result checks, code and charts showing every repeat and observed range.

https://github.com/Gr1gorii/processing-efficiency-study
