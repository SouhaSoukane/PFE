SOQL_EXAMPLES = {
    "child_to_parent": [
        "SELECT Contact.FirstName, Contact.Account.Name FROM Contact",
        "SELECT Id, Name, Account.Name FROM Contact WHERE Account.Industry = 'media'"
    ],
    "parent_to_child": [
        "SELECT Name, (SELECT LastName FROM Contacts) FROM Account",
        "SELECT Account.Name, (SELECT Contact.LastName FROM Account.Contacts) FROM Account"
    ],
    "parent_to_child_with_where": [
        "SELECT Name, (SELECT LastName FROM Contacts WHERE CreatedBy.Alias = 'x') FROM Account WHERE Industry = 'media'"
    ],
    "custom_objects": [
        "SELECT Id, FirstName__c, Mother_of_Child__r.FirstName__c FROM Daughter__c WHERE Mother_of_Child__r.LastName__c LIKE 'C%'",
        "SELECT Name, (SELECT Name FROM Line_Items__r) FROM Merchandise__c WHERE Name LIKE 'Acme%'"
    ],
    "polymorphic": [
        "SELECT Id, Owner.Name FROM Task WHERE Owner.FirstName like 'B%'",
        "SELECT Id, Who.FirstName, Who.LastName FROM Task WHERE Owner.FirstName LIKE 'B%'",
        "SELECT Id, What.Name FROM Event",
        "SELECT TYPEOF What WHEN Account THEN Phone, NumberOfEmployees WHEN Opportunity THEN Amount, CloseDate ELSE Name, Email END FROM Event"
    ],
    "with_aggregates": [
        "SELECT Name, (SELECT CreatedBy.Name FROM Notes) FROM Account",
        "SELECT Amount, Id, Name, (SELECT Quantity, ListPrice, PricebookEntry.UnitPrice, PricebookEntry.Name FROM OpportunityLineItems) FROM Opportunity"
    ]
}
def detect_example_need(natural_language_query, extracted_data):
    examples_needed = set()

    relations = extracted_data.get("relations", [])
    for rel in relations:
        from_obj = rel.get("from")
        to_obj = rel.get("to")
        rel_type = rel.get("type")

        if rel_type == "Lookup":
            # Child-to-parent query (ex: PromotionalProgram__c -> POS__c via POS__r)
            examples_needed.add("child_to_parent")
        elif rel_type == "MasterDetail":
            # Parent-to-child query
            examples_needed.add("parent_to_child")

    # Polymorphic detection from the text (approximate match)
    if "owner." in natural_language_query.lower() or "who." in natural_language_query.lower() or "what." in natural_language_query.lower():
        examples_needed.add("polymorphic")

    return list(examples_needed)
