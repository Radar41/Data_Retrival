function [children, rawResponse] = fred_category_children(categoryID)
%FRED_CATEGORY_CHILDREN Retrieve direct FRED child categories.
%
% children = fred_category_children(categoryID)
% [children, rawResponse] = fred_category_children(categoryID)
%
% Input:
%   categoryID - Numeric scalar FRED category identifier.
%                Use 0 for the FRED root category.
%
% Outputs:
%   children    - Table with columns:
%                 CategoryID, Name, ParentID
%   rawResponse - Decoded MATLAB struct returned by fred_api_request.
%
% Dependency:
%   fred_api_request.m
%
% This function retrieves exactly one FRED category level.

arguments
    categoryID (1,1) double {mustBeInteger, mustBeNonnegative}
end

rawResponse = fred_api_request( ...
    "category/children", ...
    struct( ...
        "category_id", categoryID, ...
        "file_type", "json"));

if ~isfield(rawResponse, "categories")
    error("Data_Retrival:FRED:MissingCategories", ...
        "FRED did not return a categories field for category ID %d.", ...
        categoryID);
end

categories = rawResponse.categories;

if isempty(categories)
    children = table( ...
        zeros(0,1), ...
        strings(0,1), ...
        zeros(0,1), ...
        VariableNames = ["CategoryID", "Name", "ParentID"]);

    return
end

if isstruct(categories)
    childCategoryID = reshape([categories.id], [], 1);
    categoryName = string(reshape({categories.name}, [], 1));
    parentID = reshape([categories.parent_id], [], 1);

elseif iscell(categories)
    n = numel(categories);

    childCategoryID = zeros(n, 1);
    categoryName = strings(n, 1);
    parentID = zeros(n, 1);

    for k = 1:n
        item = categories{k};

        if ~isstruct(item) || ...
                ~isfield(item, "id") || ...
                ~isfield(item, "name") || ...
                ~isfield(item, "parent_id")

            error("Data_Retrival:FRED:UnexpectedCategoryItem", ...
                "FRED returned an unexpected category item at index %d.", k);
        end

        childCategoryID(k) = double(item.id);
        categoryName(k) = string(item.name);
        parentID(k) = double(item.parent_id);
    end

else
    error("Data_Retrival:FRED:UnexpectedCategoriesType", ...
        "FRED categories response has unsupported type '%s'.", ...
        class(categories));
end

children = table( ...
    childCategoryID, ...
    categoryName, ...
    parentID, ...
    VariableNames = ["CategoryID", "Name", "ParentID"]);

end