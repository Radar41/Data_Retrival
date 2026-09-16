function config = totbkcrnsa_arima_110_evaluation_config(projectRoot)

arguments
    projectRoot (1,1) string
end

config = struct();

config.adapter_id = "matlab.arima";

config.model_id = "totbkcrnsa_level_arima_110_v1";
config.model_family = "nonseasonal_arima";
config.structure_id = "arima_110";
config.schema_version = "v1";

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

config.target_dimension = 1;
config.forecast_strategy = "recursive";
config.forecast_scale = "LEVEL";

config.arima_p = 1;
config.arima_d = 1;
config.arima_q = 0;

config.state_representation = "backend_arima_state";
config.state_dimension = NaN;
config.state_components = strings(0, 1);

config.transition_engine = ...
    "nonseasonal_arima_lag_polynomial";

config.observation_engine = ...
    "arima_observation_equation";

config.state_update_mode = "backend_native";
config.initialization_policy = "backend_default";

config.estimation_method = "maximum_likelihood";
config.estimate_parameters = true;

config.parameter_schema = [ ...
    "constant"
    "ar_1"
    "innovation_variance"];

config.fixed_parameters = struct();

config.estimated_parameters = [ ...
    "constant"
    "ar_1"
    "innovation_variance"];

config.parameter_constraints = ...
    "ar_stationarity_and_nonnegative_innovation_variance";

config.training_window_policy = "expanding";
config.minimum_training_observations = 10;
config.missing_value_policy = "reject_nonfinite";

config.forecast_distribution_kind = "normal";
config.forecast_distribution_method = "arima_forecast_mse";

config.prediction_interval_levels = [0.80 0.95];
config.prediction_interval_method = "normal_quantile";

config.residual_kind = "forecast_error";
config.residual_formula = "actual_value_minus_point_forecast";
config.residual_scale = "LEVEL";

end