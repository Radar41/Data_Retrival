function physicalType = physical_type(declaredType, dialect)
%PHYSICAL_TYPE Type a DBMS actually stores for a declared (DDL) type.
%
% dbdesign.physical_type("BOOLEAN", "mysql")      -> "TINYINT(1)"
% dbdesign.physical_type("DECIMAL(24,8)", "postgresql") -> "NUMERIC(24,8)"
%
% The DDL in sql/ is written with ANSI type names. PostgreSQL and
% MySQL/MariaDB accept them but store some under their own names; physical
% design diagrams show the stored type.

arguments
    declaredType (1,1) string
    dialect (1,1) string {mustBeMember(dialect, ["logical", "postgresql", "mysql"])}
end

declaredType = upper(strtrim(declaredType));
physicalType = declaredType;

switch dialect

    case "postgresql"

        physicalType = regexprep(physicalType, "^DECIMAL", "NUMERIC");

        if physicalType == "TIMESTAMP"
            physicalType = "TIMESTAMP (no tz)";
        end

    case "mysql"

        switch physicalType
            case "INTEGER"
                physicalType = "INT";
            case "BOOLEAN"
                physicalType = "TINYINT(1)";
        end

end

end
