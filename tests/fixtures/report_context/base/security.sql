CREATE PROCEDURE dbo.Lookup @input nvarchar(80) AS
BEGIN
    DECLARE @query nvarchar(max) = N'SELECT ' + @input;
    EXEC(@query);
END;
