CREATE PROCEDURE dbo.FindUser @input nvarchar(80)
AS
BEGIN
    DECLARE @query nvarchar(max) = N'SELECT * FROM dbo.Users WHERE Name = ' + @input;
    EXEC(@query);
END;
