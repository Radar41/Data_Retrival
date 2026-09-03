function levelOne = fred_category_level_one_build()
%FRED_CATEGORY_LEVEL_ONE_BUILD Retrieve children of all root FRED categories.
%
% levelOne = fred_category_level_one_build()
%
% Output:
%   levelOne - Table containing all direct children of the eight root
%              FRED categories.
%
% Dependencies:
%   fred_category_children.m
%   fred_api_request.m
%
% This function retrieves exactly one level below the FRED root. It does
% not recursively crawl the full FRED category hierarchy.

rootChildren = fred_category_children(0);

allChildren = table( ...
    zeros(0,1), ...
    strings(0,1), ...
    zeros(0,1), ...
    VariableNames = ["CategoryID", "Name", "ParentID"]);

for k = 1:height(rootChildren)
    parentID = rootChildren.CategoryID(k);
    parentName = rootChildren.Name(k);

    fprintf("Retrieving children of %s (%d)...\n", ...
        parentName, parentID);

    children = fred_category_children(parentID);

    if ~isempty(children)
        allChildren = [allChildren; children];
    end
end

levelOne = unique(allChildren, "rows", "stable");

fprintf("\nLevel-one categories retrieved: %d\n", ...
    height(levelOne));

end