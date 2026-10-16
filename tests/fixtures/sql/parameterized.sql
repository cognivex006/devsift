DECLARE @query nvarchar(max) = N'SELECT * FROM dbo.Users WHERE Name = @name';
EXEC sys.sp_executesql @stmt = @query, @params = N'@name nvarchar(80)', @name = @input;
