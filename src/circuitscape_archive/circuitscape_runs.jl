using ArgParse
using Circuitscape

function parse_commandline()
    s = ArgParseSettings()

    @add_arg_table s begin
        "tile_dir"
        help = "folder containing processed tile data for circuitscape"
        required = true
    end

    return parse_args(s)
end

function main()
    parsed_args = parse_commandline()

    directions = ["we", "ew", "ns", "sn"]
    # Iterate through folders
    for tile_folder in filter(isdir, readdir(parsed_args["tile_dir"], join=true))
        # Get the name of the folder
        tile_name = basename(tile_folder)
        println("Processing tile: $tile_name")

        # Iterate through directions
        for direction in directions
            println("Processing direction: $direction")
            # Construct the path to the input file
            ini_file = joinpath(tile_folder, "$direction.ini")
            println("Input file: $ini_file")

            # Check if the input file exists
            if isfile(ini_file)
                # Run Circuitscape
                Circuitscape.compute(ini_file)
            else
                println("Input file does not exist: $ini_file")
            end
        end
    end
end

main()
