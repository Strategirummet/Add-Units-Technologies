import pandas as pd
from dateutil.relativedelta import relativedelta


def Missing_Technologies(df):
    
    Energy = ["Wind",                                                       # 0
              "Solar",                                                      # 1
              "Biogas",                                                     # 2
              "Biomass",                                                    # 3
              "Coal",                                                       # 4
              "Gas",                                                        # 5
              "Geothermal",                                                 # 6
              "Hydro",                                                      # 7
              "Hydrogen",                                                   # 8
              "Marine energy",                                              # 9
              "Nuclear",                                                    # 10
              "Oil",                                                        # 11
              "Storage",                                                    # 12
              "Heat",                                                       # 13
              "Electricity storage",                                        # 14
              'Thermal storage']                                            # 15
                                                
    
                                                                            # Matching With following:
    Technology = ["Off-shore",                                              # 0                 
                  "PV",                                                     # 1
                  "Combustion Engine",                                      # 2
                  "Steam",                                                  # 3
                  "Subcritical",                                            # 4
                  "GT",                                                     # 5
                  "Binary cycle",                                           # 6
                  "Run-of-river",                                           # 7
                  "Fuel Cell",                                              # 8
                  "Wave",                                                   # 9
                  "PWR",                                                    # 10
                  "Combustion Engine",                                      # 11
                  "Battery",                                                # 12
                  "Combustion Engine",                                      # 13
                  "Battery",                                                # 14
                  'Other thermal ']                                         # 15


    
    Category = ["Thermal",                                                  # 0 
                "Hybrid",                                                   # 1
                "Renewables",                                               # 2
                "Nuclear",                                                  # 3
                "Storage"]                                                  # 4                  
    
    Technology_Category = ["Combustion Engine",                             # 0
                           "PV",                                            # 1
                           "Off-shore",                                     # 2
                           "PWR",                                           # 3 
                           "Battery"]                                       # 4  

    Energy1 = [
        "Oil",                                                              # 0
        "Solar",                                                            # 1
        "Wind",                                                             # 2
        "Nuclear",                                                          # 3
        "Electricity Storage"]                                              # 4
    
    
    print("Starting Corrigation for missing Technologies")
    print("Running Loop")                                                   # <- Print Progess

    for i in range(len(df["Technology"])):                                  # Running a Loop over Dataframe
        
        n = 0     
        j = 0                 
        if df.iloc[i]["Technology"] != df.iloc[i]["Technology"]:            # If the value is NaN          
        
            if df.iloc[i]["Energy 1"] == df.iloc[i]["Energy 1"]:            # If there is value in Energy 1

                while df.iloc[i]["Energy 1"] != Energy[n]:                  # Running a While loop until
                    n += 1                                                  # the right value of Energy 1 is found
    
                df.at[i,"Technology"] = Technology[n]                       # Replace the NaN value.

                
            elif df.iloc[i]["Energy 1"] != df.iloc[i]["Energy 1"]:          # If there is not a value in Energy 1
         
                while df.iloc[i]["Category"] != Category[j]:                # Find the coresponding category value
                    j += 1   
                    
                df.at[i,"Technology"] = Technology_Category[j]              # Replace the NaN value
            
                

        # If there is not a value in Energy 1
        # Then insert a value in Energy 1 based on Technology
        if df.iloc[i]["Energy 1"] != df.iloc[i]["Energy 1"]: 

            while df.iloc[i]["Technology"] != Technology_Category[j]:       # Find the coresponding technology value
                j += 1  

            df.at[i,"Energy 1"] = Energy1[j]              # Replace the NaN value   


    print("Completed Corrigation for missing Technologies")                 # <- Print Progress

    # Unit Status Operations
    Not_working = ["Stopped", "Cancelled", "Mothballed", "Frozen", "Suspended"]
    Working =     ["Operational", "Syncronized"]
    
    # Loop over the Data to fill empty gaps
    for i in range(len(df["Date of Commissioning"])):

        # If there is no Commissioning, but there is a decommissiong year
        if df["Date of Commissioning"][i] != df["Date of Commissioning"][i] and df["Date of Decommissioning"][i] == df["Date of Decommissioning"][i]:
            df.at[i, "Date of Commissioning"]  = df["Date of Decommissioning"][i] - relativedelta(years=20)

        # If there is no Commissioning and the unit status is closed 
        if df["Date of Commissioning"][i] != df["Date of Commissioning"][i] and df["Unit status"][i] in Not_working:
            df.at[i, "Date of Commissioning"] = pd.Timestamp(year=1900,month=12, day=31)

        # If there is no Commissioning and the unit status is working 
        if df["Date of Commissioning"][i] != df["Date of Commissioning"][i] and df["Unit status"][i] in Working:
            df.at[i, "Date of Commissioning"] = pd.Timestamp(year=2010,month=12, day=31)

        # If there is no Commissioning and there is a unit status. Then it is a future project.
        if df["Date of Commissioning"][i] != df["Date of Commissioning"][i] and df["Unit status"][i] == df["Unit status"][i]:
            df.at[i, "Date of Commissioning"] = pd.Timestamp(year=2025,month=12, day=31)

        # Find if there still is values which are not Time
        if df["Date of Commissioning"][i] != df["Date of Commissioning"][i] or isinstance(df["Date of Commissioning"][i], str):
            df.at[i, "Date of Commissioning"] = pd.Timestamp(year=2000,month=12, day=31)

        # If the year is before 1900 
        if df["Date of Commissioning"][i] < pd.Timestamp(year=1900,month=1, day=1):
            df.at[i, "Date of Commissioning"] = pd.Timestamp(year=1900,month=1, day=1)

    print("Finished Corrigation for missing Technologies")
    return df
