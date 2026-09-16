classdef (Abstract) DynamicModelAdapter < handle
    properties (SetAccess = protected)
        ModelConfig
    end

    methods
        function obj = DynamicModelAdapter(modelConfig)
            if nargin > 0
                obj.ModelConfig = modelConfig;
            end
        end
    end

    methods (Abstract)
        validation = validate(obj, dataContext)

        fitPayload = fit(obj, trainingData, fitContext)

        forecastPayload = forecast(obj, fitPayload, forecastContext)
    end
end
