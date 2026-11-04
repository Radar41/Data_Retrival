function project_shutdown()
%PROJECT_SHUTDOWN Runs when the Data_Retrival MATLAB project closes.
%   Reports what is out of sync; changes nothing. Pushing, exporting and
%   importing are deliberate actions (git, run_all.sh), not side effects.

root = currentProject().RootFolder;

[~, status] = system(sprintf('git -C "%s" status --short', root));
status = strtrim(status);
if strlength(status) > 0
    fprintf("Data_Retrival: uncommitted changes\n%s\n", status);
else
    fprintf("Data_Retrival: working tree clean\n");
end

[~, ahead] = system(sprintf('git -C "%s" rev-list --count @{u}..HEAD 2>/dev/null', root));
ahead = str2double(strtrim(ahead));
if ~isnan(ahead) && ahead > 0
    fprintf("Data_Retrival: %d commit(s) not pushed\n", ahead);
end

staging = fullfile(root, "data", "staging", "neo4j-import", "fred_catalog");
if isfolder(staging)
    files = dir(fullfile(staging, "*.csv"));
    if ~isempty(files)
        newest = max([files.datenum]);
        fprintf("Data_Retrival: %d catalog CSV(s) staged, newest %s. Run ./run_all.sh graph to import.\n", ...
            numel(files), datestr(newest, "yyyy-mm-dd HH:MM"));
    end
end
end
