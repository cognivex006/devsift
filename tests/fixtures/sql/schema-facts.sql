CREATE TABLE dbo.ExistingSchema (Id int);
GO
CREATE VIEW dbo.ExplicitView AS SELECT Id FROM dbo.ExistingSchema;
GO
SELECT * FROM UnqualifiedTable;
SELECT * FROM dbo.ExistingSchema;
DROP VIEW dbo.ExplicitView;
DROP TABLE dbo.ExistingSchema;
