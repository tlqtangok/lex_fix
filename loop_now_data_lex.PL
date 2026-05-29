#   20 pytho lex_editor.py --help 
#   17 python lex_editor.py --help  
#   16 python lex_editor.py  --input C:\Users\tlqta\AppData\Roaming\Microsoft\InputMethod\Chs\ChsWubiEUDPv1.lex --op search --query now --by code
#   15 python lex_editor.py  --input C:\Users\tlqta\AppData\Roaming\Microsoft\InputMethod\Chs\ChsWubiEUDPv1.lex --op search --query date --by code
#   12 python lex_editor.py  --input %lex% --op search --query now --by code
#   11 python lex_editor.py  --input %lex% --op search --query date --by code
#    9 python lex_editor.py --input user.lex --output out.lex --op edit --key now --value __now__ 
#    8 python lex_editor.py --input %lex% --output out.lex --op edit --key now --value __now__ 
#    7 python lex_editor.py --input %lex% --output out.lex --op edit --key now --value ___now___ 
#    6 python lex_editor.py --input %lex% --output %lex% --op edit --key now --value ___now___ 
#    5 python lex_editor.py --input %lex% --output %lex% --op edit --key now --value _now_
#    4 python lex_editor.py --input %lex% --output %lex% --op edit --key now --value _now__


use POSIX qw(strftime);

my $_now_ = strftime("%Y-%m-%d %H:%M:%S", localtime);

$_now_ = q{%yyyy%-%MM%-%dd% %HH%:%mm%:%ss%};

# $_now_ =~ s/%/\^%/g;
my $_date_ = $_now_; 

$_date_ =~ s/\s.*//;

my $lex_file = "C:\\Users\\tlqta\\AppData\\Roaming\\Microsoft\\InputMethod\\Chs\\ChsWubiEUDPv1.lex";


# main_
# monitor the lex file, if change , then echo OK in console
{
# TODO: monitor the lex file, if change, then echo OK in console

    my $last_modified_time = (stat($file))[9]; # get the last modified time of the file
    
    while(1)
    {
        if (see_changes($lex_file, $last_modified_time)) 
        {
            print "see $lex_file changes\n";
            edit_lex_file();
        }
        sleep 30;
    }
}

sub edit_lex_file {
    my $cml_edit_lex_file = "python lex_editor.py --input $lex_file --output $lex_file --op edit --key now --value \"$_now_\"  --key date --value $_date_";
    # print $cml_edit_lex_file, "\n";
    system($cml_edit_lex_file);
}

sub see_changes {
    my ($file, $last_time) = @_;
    my $current_time = (stat($file))[9]; # get the last modified time of the file
    if (!defined $last_time || $current_time > $last_time) {
        return 1; # file has changed
    }
    return 0; # no change
}


