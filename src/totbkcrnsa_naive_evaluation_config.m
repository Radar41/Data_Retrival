function config = totbkcrnsa_naive_evaluation_config(projectRoot)

arguments
    projectRoot (1,1) string
end

config = struct();

config.adapter_id = "analytical.naive_random_walk";

config.normalized_csv_path = fullfile( ...
    projectRoot, ...
    "data", "staging", "normalized", "fred", "validation", ...
    "fred_public_datalist_banks_weekly_bfaf15972702", ...
    "normalized_weekly_ending_wednesday.csv");

config.source_member = "weekly,_ending_wednesday.csv";
config.series_id = "TOTBKCRNSA";
config.data_variant = "LEVEL";
config.target_transform = "identity";
config.origin_index = 2539;

end